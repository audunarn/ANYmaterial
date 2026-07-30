"""The material library: what ships, what it says about itself, and adding more."""

from __future__ import annotations

import json

import pytest

from anymaterial import (
    LibraryEntry,
    MaterialLibrary,
    MaterialSpec,
    add_to_user_library,
    builtin_library,
    dnv_c208_steel_curve,
    library,
    user_library_path,
)


def _spec(name: str = "custom", **overrides) -> MaterialSpec:
    data = {
        "name": name,
        "symmetry": "isotropic",
        "constants": {"elastic_modulus": 210.0e9, "poisson_ratio": 0.3},
        "density": 7850.0,
        "yield_stress": 355.0e6,
    }
    data.update(overrides)
    return MaterialSpec(**data)


def test_the_builtin_library_covers_every_tabulated_steel_row() -> None:
    catalogue = builtin_library()

    # One entry per grade and thickness class in the RP-C208 table: 4+3+4+3+3.
    steels = catalogue.find(category="structural steel", status="tabulated")
    assert len(steels) == 17
    assert "S355 (16 < t <= 40 mm)" in catalogue
    assert all(entry.status == "tabulated" for entry in steels)
    assert all(entry.spec.is_nonlinear for entry in steels)


def test_steel_entries_are_derived_from_the_table_not_duplicated() -> None:
    entry = builtin_library().get("S420 (16 < t <= 40 mm)")

    # The numbers live once, in the curve table; the entry resolves them.
    assert entry.spec.hardening == {"kind": "dnv_c208", "grade": "S420", "thickness": 0.028}
    assert entry.spec.hardening_curve() == dnv_c208_steel_curve("S420", 0.028)
    assert entry.spec.yield_stress == pytest.approx(402.4e6)
    assert entry.build().hardening_curve.K == pytest.approx(703.0e6)


def test_curated_entries_carry_their_source_and_are_not_design_values() -> None:
    catalogue = builtin_library()
    aluminium = catalogue.get("EN AW-6082-T6")
    stainless = catalogue.get("EN 1.4404 (316L)")

    for entry in (aluminium, stainless):
        assert entry.status == "indicative"
        assert not entry.is_design_value
        assert entry.source and entry.source.startswith("http")
        assert entry.standard
        assert entry.notes
        # No invented flow curve where none was available from a source.
        assert not entry.spec.is_nonlinear

    assert aluminium.spec.constants["elastic_modulus"] == pytest.approx(70.0e9)
    assert aluminium.spec.constants["poisson_ratio"] == pytest.approx(0.33)
    assert aluminium.spec.density == pytest.approx(2700.0)
    assert stainless.spec.constants["elastic_modulus"] == pytest.approx(200.0e9)
    assert stainless.spec.density == pytest.approx(8000.0)


def test_a_tabulated_entry_is_marked_as_a_design_value() -> None:
    assert builtin_library().get("S355 (t <= 16 mm)").is_design_value


def test_every_shipped_material_builds_and_validates() -> None:
    import numpy as np

    from anymaterial import (
        beam_material_properties,
        elastic_compliance_matrix,
        material_validation_errors,
        shell_material_matrices,
    )

    for entry in builtin_library():
        material = entry.build()
        assert material.name == entry.spec.name
        assert entry.category
        assert entry.status in ("tabulated", "measured", "indicative")
        assert material_validation_errors(material) == ()

        # Checked through the contract rather than through isotropic fields, so
        # the check still holds if an orthotropic entry is ever added back.
        compliance = elastic_compliance_matrix(material)
        assert np.all(np.linalg.eigvalsh(0.5 * (compliance + compliance.T)) > 0.0)
        # And every one reduces to something a shell and a beam can use.
        plane_stress, _transverse, _drilling = shell_material_matrices(material)
        assert np.all(np.isfinite(plane_stress))
        assert beam_material_properties(material).axial_modulus > 0.0


def test_every_shipped_curve_is_monotonic_and_finite() -> None:
    import numpy as np

    for entry in builtin_library().find(nonlinear=True):
        curve = entry.spec.hardening_curve()
        strains = np.linspace(0.0, 0.30, 301)
        stresses = np.asarray(curve.flow_stress(strains), dtype=float)
        moduli = np.asarray(curve.hardening_modulus(strains), dtype=float)

        assert np.all(np.isfinite(stresses)) and np.all(stresses > 0.0)
        # Softening would make the consistent tangent indefinite.
        assert np.all(np.diff(stresses) >= -1.0e-6)
        assert np.all(np.isfinite(moduli)) and np.all(moduli >= -1.0e-9)
        # A flow curve starts at or below the nominal yield and rises past it.
        # The RP-C208 curves start at the proportional limit, deliberately below
        # yield; the Ramberg-Osgood-derived stainless curves start at it.
        assert stresses[0] <= entry.spec.yield_stress * (1.0 + 1.0e-9)
        assert stresses[-1] > entry.spec.yield_stress


def test_derived_entries_record_how_they_were_derived() -> None:
    catalogue = builtin_library()

    stainless = catalogue.get("EN 1.4404 (316L) annealed, nonlinear indicative")
    assert stainless.calculation["n"] == pytest.approx(7.0)
    assert "sigma/E" in stainless.calculation["model"]
    # The tabulated curve came out of that model, so the exponent behind it is
    # part of the entry rather than lost at import.
    assert stainless.spec.hardening["kind"] == "piecewise_linear"

    duplex = catalogue.get("EN 1.4462 (Duplex 2205) nonlinear indicative")
    assert duplex.calculation["n"] == pytest.approx(7.0)
    # The notes say plainly that the source supports the curve form and the
    # fy/fu inputs, and that the tabulated points were computed from those.
    assert "supports the curve FORM" in duplex.notes
    assert "not taken" in duplex.notes


def test_the_calculation_record_survives_a_round_trip(tmp_path) -> None:
    catalogue = builtin_library()
    path = tmp_path / "library.json"
    catalogue.save(path)

    reloaded = MaterialLibrary.load(path)
    original = catalogue.get("EN 1.4462 (Duplex 2205) nonlinear indicative")
    restored = reloaded.get("EN 1.4462 (Duplex 2205) nonlinear indicative")

    assert restored.calculation == original.calculation
    assert restored.tensile_strength == pytest.approx(original.tensile_strength)


def test_the_library_filters_by_category_status_and_text() -> None:
    catalogue = builtin_library()

    assert catalogue.categories == (
        "aluminium",
        "cast iron",
        "composite lamina",
        "duplex stainless steel",
        "stainless steel",
        "structural steel",
    )
    assert len(catalogue.find(category="aluminium")) == 4
    assert len(catalogue.find(status="indicative")) == 9
    assert len(catalogue.find(status="tabulated")) == 17
    assert len(catalogue.find(status="measured")) == 7
    assert len(catalogue.find(nonlinear=True)) == 20
    assert len(catalogue.find(nonlinear=False)) == 13
    assert {entry.name for entry in catalogue.find(text="S460")} == {
        "S460 (t <= 16 mm)",
        "S460 (16 < t <= 40 mm)",
        "S460 (40 < t <= 63 mm)",
        "S460 NL 25 mm plate (measured mean)",
    }
    assert catalogue.find(text="unobtanium") == []


def test_a_missing_material_says_which() -> None:
    with pytest.raises(KeyError, match="no material named 'unobtanium'"):
        builtin_library().get("unobtanium")


def test_adding_a_duplicate_name_is_refused_unless_asked() -> None:
    catalogue = MaterialLibrary()
    catalogue.add(LibraryEntry(spec=_spec("mine")))

    # Two materials with one name is how the wrong one ends up in an analysis.
    with pytest.raises(ValueError, match="already in the library"):
        catalogue.add(LibraryEntry(spec=_spec("mine")))

    catalogue.add(LibraryEntry(spec=_spec("mine", density=1.0)), replace_existing=True)
    assert len(catalogue) == 1
    assert catalogue.get("mine").spec.density == pytest.approx(1.0)


def test_an_invalid_material_cannot_enter_the_library() -> None:
    catalogue = MaterialLibrary()
    bad = MaterialSpec(
        name="impossible",
        constants={"elastic_modulus": 210.0e9, "poisson_ratio": 0.9},
    )

    # Validated on the way in, so a library file can never hold something that
    # will not build.
    with pytest.raises(ValueError, match=r"-1 < nu < 0.5"):
        catalogue.add(LibraryEntry(spec=bad))
    assert len(catalogue) == 0


def test_an_unknown_status_is_refused() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        LibraryEntry(spec=_spec(), status="probably-fine")


def test_removing_and_membership() -> None:
    catalogue = MaterialLibrary()
    catalogue.add(LibraryEntry(spec=_spec("mine")))

    assert "mine" in catalogue
    assert catalogue.names == ("mine",)
    assert catalogue.remove("mine").name == "mine"
    assert "mine" not in catalogue
    with pytest.raises(KeyError):
        catalogue.remove("mine")


def test_a_library_round_trips_through_json(tmp_path) -> None:
    catalogue = builtin_library()
    path = tmp_path / "library.json"
    catalogue.save(path)

    reloaded = MaterialLibrary.load(path)
    assert reloaded.names == catalogue.names
    for original, restored in zip(catalogue, reloaded):
        assert restored.spec == original.spec
        assert restored.status == original.status
        assert restored.category == original.category
        assert restored.source == original.source
        # A curve survives because the descriptor does, not because a copy of it
        # was written out.
        assert (restored.spec.hardening_curve() is None) == (original.spec.hardening_curve() is None)


def test_a_foreign_or_versioned_document_is_refused(tmp_path) -> None:
    with pytest.raises(ValueError, match="not an anymaterial.library document"):
        MaterialLibrary.from_dict({"format": "something-else", "version": 1})
    with pytest.raises(ValueError, match="unsupported anymaterial.library version"):
        MaterialLibrary.from_dict({"format": "anymaterial.library", "version": 99})


def test_a_user_material_is_written_and_read_back(user_library) -> None:
    assert user_library_path() == user_library
    assert not user_library.exists()

    entry = LibraryEntry(
        spec=_spec("Shipyard plate", hardening={"kind": "dnv_c208", "grade": "S355", "thickness": 0.02}),
        category="structural steel",
        source="mill certificate 2026-07",
    )
    path = add_to_user_library(entry)

    assert path == user_library
    assert path.is_file()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["format"] == "anymaterial.library"
    assert stored["materials"][0]["name"] == "Shipyard plate"

    catalogue = library()
    assert "Shipyard plate" in catalogue
    restored = catalogue.get("Shipyard plate")
    assert restored.status == "user"
    assert restored.source == "mill certificate 2026-07"
    assert restored.spec.hardening_curve() == dnv_c208_steel_curve("S355", 0.02)


def test_adding_records_the_entry_as_the_users_own(user_library) -> None:
    # Even if it claims to be tabulated: what a user adds is theirs, and calling
    # it a standard's table would launder its provenance.
    add_to_user_library(LibraryEntry(spec=_spec("claimed"), status="tabulated"))

    assert library().get("claimed").status == "user"


def test_a_user_entry_overrides_a_builtin_of_the_same_name(user_library) -> None:
    name = "S355 (t <= 16 mm)"
    assert builtin_library().get(name).spec.yield_stress == pytest.approx(357.0e6)

    add_to_user_library(LibraryEntry(spec=_spec(name, yield_stress=400.0e6)))

    # How a grade gets corrected locally without editing the package.
    catalogue = library()
    assert catalogue.get(name).spec.yield_stress == pytest.approx(400.0e6)
    assert catalogue.get(name).status == "user"
    assert len(catalogue) == len(builtin_library())


def test_the_user_library_can_be_excluded(user_library) -> None:
    add_to_user_library(LibraryEntry(spec=_spec("mine")))

    assert "mine" in library()
    assert "mine" not in library(include_user=False)


def test_adding_the_same_name_twice_needs_replace(user_library) -> None:
    add_to_user_library(LibraryEntry(spec=_spec("mine")))

    with pytest.raises(ValueError, match="already in the library"):
        add_to_user_library(LibraryEntry(spec=_spec("mine")))
    add_to_user_library(LibraryEntry(spec=_spec("mine", density=10.0)), replace_existing=True)
    assert library().get("mine").spec.density == pytest.approx(10.0)


def test_the_library_path_follows_the_environment(monkeypatch, tmp_path) -> None:
    elsewhere = tmp_path / "project" / "materials.json"
    monkeypatch.setenv("ANYMATERIAL_LIBRARY", str(elsewhere))

    assert user_library_path() == elsewhere
    add_to_user_library(LibraryEntry(spec=_spec("project steel")))
    # Written beside the project rather than in a home directory.
    assert elsewhere.is_file()


def test_measured_entries_carry_their_scatter_and_attribution() -> None:
    # The steel entries all come from one campaign database and share a shape.
    entries = [
        entry
        for entry in builtin_library().find(status="measured")
        if entry.category == "structural steel"
    ]
    assert len(entries) == 6

    for entry in entries:
        record = entry.measurement
        assert record["coupons"] >= 5
        assert 0.0 < record["yield_stress_cov"] < 0.2
        assert 0.0 < record["elastic_modulus_cov"] < 0.2
        assert record["license"] == "CC-BY-4.0"
        assert "Hartloper" in record["citation"] and "10.5281/zenodo.6965147" in record["citation"]
        assert entry.source == "https://doi.org/10.5281/zenodo.6965147"
        assert record["campaign"] and record["product_form"]
        # A mean is not a characteristic value, and the entry says so.
        assert "not a characteristic or design value" in entry.notes
        assert not entry.is_design_value


def test_a_measured_mean_exceeds_the_nominal_grade_yield() -> None:
    catalogue = builtin_library()
    measured = catalogue.get("S355 J2+N 15 mm plate (measured mean)")
    tabulated = catalogue.get("S355 (t <= 16 mm)")

    # 411.7 MPa measured against 357 MPa tabulated: this is exactly why using a
    # campaign mean as a design strength is unconservative, and why the two
    # statuses are kept apart.
    assert measured.spec.yield_stress > tabulated.spec.yield_stress
    assert tabulated.is_design_value and not measured.is_design_value


def test_a_measured_entry_without_its_scatter_is_refused() -> None:
    with pytest.raises(ValueError, match="carries no measurement record"):
        LibraryEntry(spec=_spec("claimed measurement"), status="measured")

    # With the record, it is accepted.
    LibraryEntry(
        spec=_spec("real measurement"),
        status="measured",
        measurement={"coupons": 5, "yield_stress_cov": 0.03},
    )


def test_every_shipped_entry_names_a_source() -> None:
    for entry in builtin_library():
        assert entry.source, f"{entry.name} has no source"
        assert entry.standard, f"{entry.name} has no standard"
        assert entry.notes, f"{entry.name} has no notes"


def test_the_lamina_separates_what_was_measured_from_what_was_assumed() -> None:
    entry = builtin_library().get("IM7/8552 UD lamina, RTD (measured mean)")

    assert entry.status == "measured"
    assert entry.category == "composite lamina"
    assert entry.spec.symmetry == "orthotropic"
    assert "NCAMP" in entry.measurement["citation"]
    assert entry.measurement["condition"].startswith("RTD")
    assert entry.measurement["prepreg_lots"] == 3

    # Four constants measured, five following from an assumption, and the entry
    # says which is which rather than presenting nine equal-looking numbers.
    assert "E1, E2, G12, nu12" in entry.calculation["measured"]
    assert "transverse isotropy" in entry.calculation["assumption"]
    assert "assumed 0.45" in entry.calculation["nu23"]

    constants = entry.spec.constants
    assert constants["elastic_modulus_1"] == pytest.approx(23.51 * 6.894757e9, rel=1e-6)
    assert constants["elastic_modulus_3"] == pytest.approx(constants["elastic_modulus_2"])
    assert constants["shear_modulus_13"] == pytest.approx(constants["shear_modulus_12"])
    # G23 = E2 / 2(1 + nu23) is exact for transverse isotropy.
    assert constants["shear_modulus_23"] == pytest.approx(
        constants["elastic_modulus_2"] / (2.0 * (1.0 + constants["poisson_ratio_23"])), rel=1e-6
    )


def test_the_lamina_declares_no_yield_and_no_failure_criterion() -> None:
    entry = builtin_library().get("IM7/8552 UD lamina, RTD (measured mean)")

    # Composite failure is not isotropic yielding, so a plausible-looking yield
    # number here would be quietly misused.
    assert entry.spec.yield_stress == pytest.approx(0.0)
    assert not entry.spec.is_nonlinear
    assert "defines no failure criterion" in entry.notes
    assert "not a design allowable" in entry.notes


def test_the_lamina_satisfies_poisson_reciprocity() -> None:
    constants = builtin_library().get("IM7/8552 UD lamina, RTD (measured mean)").spec.constants

    # nu21 = nu12 * E2 / E1.  The qualification programme separately measured a
    # transverse-compression nu21 of 0.024, so 0.017 is the right order and the
    # data set is self-consistent.
    nu21 = (
        constants["poisson_ratio_12"]
        * constants["elastic_modulus_2"]
        / constants["elastic_modulus_1"]
    )
    assert nu21 == pytest.approx(0.0175, abs=5.0e-4)
