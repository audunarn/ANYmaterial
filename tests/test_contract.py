"""The structural material contract, its reductions and its validation.

Migrated from ``ANYsolver/tests/test_orthotropic_material_contract.py``.  The
tests that exercised solver model registration stayed behind with the solver;
what remains is the material behaviour itself, plus the duck-typing property
that makes cross-package registration possible in the first place.
"""

from __future__ import annotations

import numpy as np
import pytest

from anymaterial import (
    ENGINEERING_VOIGT_ORDER,
    Hill48Yield,
    IsotropicMaterial,
    OrthotropicMaterial,
    StructuralMaterial,
    beam_material_properties,
    elastic_compliance_matrix,
    hill48_coefficients,
    hill48_equivalent_stress,
    is_isotropic_material,
    is_orthotropic_material,
    material_validation_errors,
    shell_characteristic_modulus,
    shell_material_matrices,
    validate_material,
)


def _orthotropic(**overrides) -> OrthotropicMaterial:
    properties = {
        "name": "ud",
        "elastic_modulus_1": 150.0e9,
        "elastic_modulus_2": 10.0e9,
        "elastic_modulus_3": 8.0e9,
        "poisson_ratio_12": 0.25,
        "poisson_ratio_13": 0.20,
        "poisson_ratio_23": 0.30,
        "shear_modulus_12": 5.0e9,
        "shear_modulus_13": 4.0e9,
        "shear_modulus_23": 3.0e9,
        "density": 1600.0,
    }
    properties.update(overrides)
    return OrthotropicMaterial(**properties)


def test_isotropic_material_satisfies_contract_and_compliance() -> None:
    material = IsotropicMaterial("steel", 210.0e9, 0.3, density=7850.0)

    assert isinstance(material, StructuralMaterial)
    assert material.elastic_symmetry == "isotropic"
    assert is_isotropic_material(material)
    assert not is_orthotropic_material(material)
    assert ENGINEERING_VOIGT_ORDER == ("11", "22", "33", "23", "13", "12")

    compliance = elastic_compliance_matrix(material)
    assert compliance.shape == (6, 6)
    assert np.allclose(compliance, compliance.T)
    assert compliance[0, 0] == pytest.approx(1.0 / material.elastic_modulus)
    assert compliance[0, 1] == pytest.approx(-material.poisson_ratio / material.elastic_modulus)
    assert compliance[5, 5] == pytest.approx(1.0 / material.shear_modulus)
    assert material.shear_modulus == pytest.approx(210.0e9 / (2.0 * 1.3))
    assert material.bulk_modulus == pytest.approx(210.0e9 / (3.0 * 0.4))
    assert not material.is_nonlinear


def test_orthotropic_compliance_reciprocity_and_reduced_properties() -> None:
    material = _orthotropic()

    assert isinstance(material, StructuralMaterial)
    assert is_orthotropic_material(material)
    compliance = material.elastic_compliance_matrix()
    assert np.allclose(compliance, compliance.T)
    assert compliance[0, 1] == pytest.approx(-material.poisson_ratio_12 / material.elastic_modulus_1)
    assert material.poisson_ratio_21 / material.elastic_modulus_2 == pytest.approx(
        material.poisson_ratio_12 / material.elastic_modulus_1
    )
    assert np.all(np.linalg.eigvalsh(compliance) > 0.0)

    plane_stress, transverse_shear, drilling_shear = shell_material_matrices(material)
    expected_plane_stress = np.linalg.inv(compliance[np.ix_((0, 1, 5), (0, 1, 5))])
    assert np.allclose(plane_stress, expected_plane_stress)
    assert np.allclose(transverse_shear, np.diag([material.shear_modulus_13, material.shear_modulus_23]))
    assert drilling_shear == pytest.approx(material.shear_modulus_12)

    beam = beam_material_properties(material)
    assert beam.axial_modulus == pytest.approx(material.elastic_modulus_1)
    assert beam.shear_modulus_xy == pytest.approx(material.shear_modulus_12)
    assert beam.shear_modulus_xz == pytest.approx(material.shear_modulus_13)
    assert beam.characteristic_modulus == pytest.approx(material.elastic_modulus_1)

    assert shell_characteristic_modulus(material) == pytest.approx(material.elastic_modulus_1)


def test_plane_stress_inverts_compliance_rather_than_reducing_stiffness() -> None:
    # Deleting the third row and column of the 3D stiffness gives plane strain,
    # which is stiffer.  This pins the distinction numerically so a future
    # "simplification" of shell_material_matrices cannot quietly make the shell
    # overstiff -- the classic factor is 1/(1 - nu^2) on the diagonal.
    E, nu = 210.0e9, 0.3
    material = IsotropicMaterial("iso", E, nu)
    plane_stress, _transverse, _drilling = shell_material_matrices(material)

    assert plane_stress[0, 0] == pytest.approx(E / (1.0 - nu**2))
    assert plane_stress[0, 1] == pytest.approx(nu * E / (1.0 - nu**2))
    assert plane_stress[2, 2] == pytest.approx(material.shear_modulus)

    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    plane_strain_11 = lam + 2.0 * material.shear_modulus
    assert plane_stress[0, 0] < plane_strain_11


def test_orthotropic_isotropic_limit_matches_isotropic_reductions() -> None:
    E = 70.0e9
    nu = 0.25
    G = E / (2.0 * (1.0 + nu))
    isotropic = IsotropicMaterial("iso", E, nu)
    orthotropic = OrthotropicMaterial("ortho_iso", E, E, E, nu, nu, nu, G, G, G)

    assert np.allclose(
        elastic_compliance_matrix(orthotropic),
        elastic_compliance_matrix(isotropic),
    )
    iso_shell = shell_material_matrices(isotropic)
    ortho_shell = shell_material_matrices(orthotropic)
    assert all(np.allclose(left, right) for left, right in zip(iso_shell, ortho_shell))
    assert beam_material_properties(orthotropic) == pytest.approx(
        beam_material_properties(isotropic)
    )


def test_orthotropic_validation_rejects_invalid_moduli_and_compliance() -> None:
    with pytest.raises(ValueError, match="elastic_modulus_2 must be finite and positive"):
        _orthotropic(elastic_modulus_2=0.0)

    with pytest.raises(ValueError, match="positive definite"):
        _orthotropic(poisson_ratio_12=4.0)

    with pytest.raises(ValueError, match="density must be finite and non-negative"):
        _orthotropic(density=-1.0)

    with pytest.raises(ValueError, match="hardening_curve requires hill_yield"):
        _orthotropic(hardening_curve=object())


def test_isotropic_validation_rejects_inadmissible_constants() -> None:
    with pytest.raises(ValueError, match="elastic modulus must be finite and positive"):
        IsotropicMaterial("bad", -1.0, 0.3)
    with pytest.raises(ValueError, match=r"-1 < nu < 0.5"):
        IsotropicMaterial("bad", 210.0e9, 0.5)
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        IsotropicMaterial("   ", 210.0e9, 0.3)


def test_hill48_coefficients_reproduce_all_six_strengths() -> None:
    hill = Hill48Yield(X=400.0e6, Y=320.0e6, Z=280.0e6, S12=190.0e6, S13=175.0e6, S23=160.0e6)
    strengths = (hill.X, hill.Y, hill.Z, hill.S23, hill.S13, hill.S12)
    for index, strength in enumerate(strengths):
        stress = np.zeros(6)
        stress[index] = strength
        assert hill.utilization(stress) == pytest.approx(1.0)

    stress = np.array([hill.X, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert hill.equivalent_stress(stress) == pytest.approx(hill.X)
    assert hill48_equivalent_stress(stress, hill) == pytest.approx(hill.X)
    assert np.allclose(
        hill.plane_stress_quadratic_matrix(),
        hill.quadratic_form_matrix()[np.ix_((0, 1, 5), (0, 1, 5))],
    )

    coefficients = hill48_coefficients(hill)
    assert (coefficients["F"], coefficients["G"], coefficients["H"]) == pytest.approx(
        hill.coefficients()[:3]
    )
    assert (coefficients["L"], coefficients["M"], coefficients["N"]) == pytest.approx(
        hill.coefficients()[3:]
    )

    with pytest.raises(ValueError, match="finite and positive"):
        Hill48Yield(1.0, 1.0, 1.0, 1.0, 0.0, 1.0)
    with pytest.raises(ValueError, match="convex"):
        Hill48Yield(1.0, 10.0, 10.0, 1.0, 1.0, 1.0)


def test_hill48_isotropic_limit_is_von_mises() -> None:
    yield_stress = 355.0e6
    shear_yield = yield_stress / np.sqrt(3.0)
    hill = Hill48Yield(
        yield_stress, yield_stress, yield_stress, shear_yield, shear_yield, shear_yield
    )
    stress = np.array([240.0e6, -35.0e6, 80.0e6, 12.0e6, -9.0e6, 45.0e6])
    s1, s2, s3, t23, t13, t12 = stress
    von_mises = np.sqrt(
        0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2)
        + 3.0 * (t23**2 + t13**2 + t12**2)
    )

    assert hill.equivalent_stress(stress) == pytest.approx(von_mises)
    assert hill48_equivalent_stress(stress, hill) == pytest.approx(von_mises)


def test_hill48_evaluates_a_whole_field_at_once() -> None:
    hill = Hill48Yield(400.0e6, 320.0e6, 280.0e6, 190.0e6, 175.0e6, 160.0e6)
    field = np.zeros((4, 3, 6))
    field[..., 0] = hill.X

    assert hill48_equivalent_stress(field, hill).shape == (4, 3)
    assert np.allclose(hill48_equivalent_stress(field, hill), hill.X)
    assert np.allclose(hill.utilization(field), 1.0)


def test_hill48_serializes_and_reloads() -> None:
    hill = Hill48Yield(400.0e6, 320.0e6, 280.0e6, 190.0e6, 175.0e6, 160.0e6)

    assert Hill48Yield.from_dict(hill.as_dict()) == hill
    with pytest.raises(ValueError, match="require all of"):
        Hill48Yield.from_dict({"X": 1.0})


class _ExternalOrthotropicMaterial:
    """A material defined outside this package, satisfying only the protocol."""

    def __init__(self, name: str = "external") -> None:
        self.name = name
        self.density = 1234.0
        self.elastic_symmetry = "orthotropic"
        self._compliance = _orthotropic().elastic_compliance_matrix()

    def elastic_compliance_matrix(self) -> np.ndarray:
        return self._compliance.copy()


def test_validation_accepts_a_material_that_never_imported_this_package() -> None:
    external = _ExternalOrthotropicMaterial()

    assert isinstance(external, StructuralMaterial)
    validate_material(external)
    assert material_validation_errors(external) == ()

    plane_stress, _transverse, _drilling = shell_material_matrices(external)
    assert np.allclose(plane_stress, shell_material_matrices(_orthotropic())[0])


def test_general_anisotropy_is_refused_explicitly() -> None:
    anisotropic = _ExternalOrthotropicMaterial("general")
    anisotropic.elastic_symmetry = "anisotropic"

    errors = material_validation_errors(anisotropic)
    assert any("general anisotropic elasticity is not supported" in message for message in errors)
    with pytest.raises(ValueError, match="general anisotropic elasticity is not supported"):
        validate_material(anisotropic)
    with pytest.raises(NotImplementedError, match="not supported"):
        shell_material_matrices(anisotropic)
    with pytest.raises(NotImplementedError, match="not supported"):
        beam_material_properties(anisotropic)


def test_undeclared_symmetry_is_refused_but_legacy_fields_still_resolve() -> None:
    class _Undeclared:
        name = "mystery"
        density = 1.0

        def elastic_compliance_matrix(self) -> np.ndarray:
            return np.eye(6)

    errors = material_validation_errors(_Undeclared())
    assert any("must declare elastic_symmetry" in message for message in errors)

    class _LegacyIsotropic:
        name = "legacy"
        density = 7850.0
        elastic_modulus = 210.0e9
        poisson_ratio = 0.3

    legacy = _LegacyIsotropic()
    assert is_isotropic_material(legacy)
    compliance = elastic_compliance_matrix(legacy)
    assert compliance[0, 0] == pytest.approx(1.0 / 210.0e9)
    assert material_validation_errors(legacy) == ()
