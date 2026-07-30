"""Serializable material specifications.

The property that matters throughout: a material that goes to a file and comes
back must be the same material.  A specification that silently dropped its
hardening would reload as elastic and turn a plastic analysis into a different
analysis without saying so, so the round trip is tested for every curve kind and
the failure to describe a curve is tested to raise.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from anymaterial import (
    Hill48Yield,
    IsotropicMaterial,
    LinearHardeningCurve,
    MaterialSpec,
    OrthotropicMaterial,
    PiecewiseLinearCurve,
    PowerLawHardeningCurve,
    build_hardening_curve,
    dnv_c208_steel_curve,
    elastic_compliance_matrix,
    hardening_descriptor,
    load_specs,
    save_specs,
    spec_from_material,
    steel,
)


def _isotropic_spec(**overrides) -> MaterialSpec:
    data = {
        "name": "steel",
        "symmetry": "isotropic",
        "constants": {"elastic_modulus": 210.0e9, "poisson_ratio": 0.3},
        "density": 7850.0,
        "yield_stress": 355.0e6,
    }
    data.update(overrides)
    return MaterialSpec(**data)


def test_spec_builds_and_validates_an_isotropic_material() -> None:
    material = _isotropic_spec().build()

    assert isinstance(material, IsotropicMaterial)
    assert material.elastic_modulus == pytest.approx(210.0e9)
    assert not material.is_nonlinear


def test_spec_builds_an_orthotropic_material_with_hill_strengths() -> None:
    spec = MaterialSpec(
        name="ud",
        symmetry="orthotropic",
        constants={
            "elastic_modulus_1": 150.0e9,
            "elastic_modulus_2": 10.0e9,
            "elastic_modulus_3": 8.0e9,
            "poisson_ratio_12": 0.25,
            "poisson_ratio_13": 0.20,
            "poisson_ratio_23": 0.30,
            "shear_modulus_12": 5.0e9,
            "shear_modulus_13": 4.0e9,
            "shear_modulus_23": 3.0e9,
        },
        density=1600.0,
        hill={"X": 400.0e6, "Y": 320.0e6, "Z": 280.0e6, "S12": 190.0e6, "S13": 175.0e6, "S23": 160.0e6},
    )
    material = spec.build()

    assert isinstance(material, OrthotropicMaterial)
    assert material.hill_yield == Hill48Yield(400.0e6, 320.0e6, 280.0e6, 190.0e6, 175.0e6, 160.0e6)
    assert material.hill48_yield is material.hill_yield


def test_spec_rejects_missing_constants_and_bad_symmetry() -> None:
    with pytest.raises(ValueError, match="missing constants"):
        MaterialSpec(name="half", constants={"elastic_modulus": 210.0e9})
    with pytest.raises(ValueError, match="is not supported"):
        MaterialSpec(name="odd", symmetry="anisotropic", constants={})
    with pytest.raises(ValueError, match="non-empty string"):
        _isotropic_spec(name="  ")
    with pytest.raises(ValueError, match="require all of"):
        _isotropic_spec(hill={"X": 400.0e6})


def test_dnv_hardening_is_stored_as_a_lookup_not_a_frozen_copy() -> None:
    spec = _isotropic_spec(hardening={"kind": "dnv_c208", "grade": "S355", "thickness": 0.020})

    assert spec.is_nonlinear
    # The descriptor holds the grade and thickness, so the curve is resolved
    # through the table on every build rather than from a stored copy.
    assert json.loads(spec.to_json())["hardening"] == {
        "kind": "dnv_c208",
        "grade": "S355",
        "thickness": 0.020,
    }
    assert spec.hardening_curve() == dnv_c208_steel_curve("S355", 0.020)
    assert spec.build().hardening_curve == dnv_c208_steel_curve("S355", 0.020)


@pytest.mark.parametrize(
    "curve",
    [
        LinearHardeningCurve(355.0e6, 2000.0e6),
        PiecewiseLinearCurve.from_points([(0.0, 355.0e6), (0.02, 400.0e6), (0.1, 450.0e6)]),
        PowerLawHardeningCurve.from_yield(355.0e6, 740.0e6, 0.166),
        dnv_c208_steel_curve("S420", 0.020),
    ],
)
def test_every_curve_survives_a_descriptor_round_trip(curve) -> None:
    descriptor = hardening_descriptor(curve)

    # The descriptor must be JSON, not just dict-shaped.
    rebuilt = build_hardening_curve(json.loads(json.dumps(descriptor)))

    strains = np.linspace(0.0, 0.12, 25)
    assert np.asarray(rebuilt.flow_stress(strains)) == pytest.approx(
        np.asarray(curve.flow_stress(strains))
    )
    assert np.asarray(rebuilt.hardening_modulus(strains)) == pytest.approx(
        np.asarray(curve.hardening_modulus(strains))
    )


def test_an_undescribable_curve_raises_rather_than_serializing_as_elastic() -> None:
    class _CustomCurve:
        def flow_stress(self, eps_p):
            return np.full_like(np.asarray(eps_p, dtype=float), 355.0e6)

        def hardening_modulus(self, eps_p):
            return np.zeros_like(np.asarray(eps_p, dtype=float))

    material = IsotropicMaterial("custom", 210.0e9, 0.3, hardening_curve=_CustomCurve())

    with pytest.raises(ValueError, match="cannot serialize hardening curve"):
        spec_from_material(material)


def test_unknown_and_incomplete_descriptors_are_refused() -> None:
    assert build_hardening_curve(None) is None
    with pytest.raises(ValueError, match="unknown hardening kind"):
        build_hardening_curve({"kind": "ramberg_osgood", "sigma_yield": 355.0e6})
    with pytest.raises(ValueError, match="incomplete 'dnv_c208' hardening descriptor"):
        build_hardening_curve({"kind": "dnv_c208", "grade": "S355"})


def test_spec_from_material_round_trips_a_live_material() -> None:
    original = steel("S460", 0.030, name="deck", nonlinear=True)
    spec = spec_from_material(original)
    rebuilt = spec.build()

    assert spec.name == "deck"
    assert spec.symmetry == "isotropic"
    assert np.allclose(elastic_compliance_matrix(rebuilt), elastic_compliance_matrix(original))
    assert rebuilt.yield_stress == pytest.approx(original.yield_stress)
    assert rebuilt.density == pytest.approx(original.density)
    assert rebuilt.hardening_curve == original.hardening_curve
    assert MaterialSpec.from_dict(spec.to_dict()) == spec


def test_specs_save_and_load_through_a_file(tmp_path) -> None:
    specs = [_isotropic_spec(), _isotropic_spec(name="soft", constants={"elastic_modulus": 70.0e9, "poisson_ratio": 0.33})]
    path = tmp_path / "materials.json"

    save_specs(path, specs)
    assert [spec.name for spec in load_specs(path)] == ["steel", "soft"]
    assert load_specs(path) == specs

    # Overwriting is refused unless asked for, so a library file is not lost to
    # a mistyped filename.
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        save_specs(path, specs)
    save_specs(path, specs[:1], overwrite=True)
    assert [spec.name for spec in load_specs(path)] == ["steel"]


def test_a_single_material_object_is_a_valid_file(tmp_path) -> None:
    path = tmp_path / "one.json"
    path.write_text(_isotropic_spec().to_json(), encoding="utf-8")

    loaded = load_specs(path)
    assert len(loaded) == 1
    assert loaded[0].name == "steel"

    bad = tmp_path / "bad.json"
    bad.write_text("42", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an object or a list"):
        load_specs(bad)
