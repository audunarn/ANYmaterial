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
    steels = catalogue.find(category="structural steel")
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
    for entry in builtin_library():
        material = entry.build()
        assert material.name == entry.spec.name
        assert material.elastic_modulus > 0.0
        assert entry.category
        assert entry.status in ("tabulated", "indicative")


def test_the_library_filters_by_category_status_and_text() -> None:
    catalogue = builtin_library()

    assert catalogue.categories == ("aluminium", "stainless steel", "structural steel")
    assert len(catalogue.find(category="aluminium")) == 1
    assert len(catalogue.find(status="indicative")) == 2
    assert len(catalogue.find(nonlinear=True)) == 17
    assert len(catalogue.find(nonlinear=False)) == 2
    assert {entry.name for entry in catalogue.find(text="S460")} == {
        "S460 (t <= 16 mm)",
        "S460 (16 < t <= 40 mm)",
        "S460 (40 < t <= 63 mm)",
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
