"""Editor smoke tests.

These drive the real widgets: set the entry variables, read back the validation
message, and check the specification the form produces.  Skipped when no display
is available, which is the case on Linux CI runners.

One module-scoped root is used throughout; creating and destroying Tk roots per
test is unreliable on Windows.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from anymaterial import MaterialSpec, dnv_c208_steel_curve, load_specs, save_specs

pytest.importorskip("tkinter.ttk", reason="the editor needs a tkinter build")


@pytest.fixture(scope="module")
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for tkinter")
    window.geometry("900x560+40+40")
    window.update()
    yield window
    window.destroy()


@pytest.fixture
def editor(root):
    from anymaterial.gui import MaterialEditor

    frame = MaterialEditor(root)
    frame.pack(fill="both", expand=True)
    root.update()
    yield frame
    frame.destroy()
    root.update()


def test_editor_opens_valid_and_reports_derived_properties(editor, root) -> None:
    root.update()

    assert "valid isotropic material" in editor.status_text
    assert "shell plane stress" in editor._derived.cget("text")
    # Defaults are E = 210 GPa and nu = 0.3, so the drilling shear is E/2.6.
    assert "80.769" in editor._derived.cget("text")


def test_editor_reports_an_inadmissible_poisson_ratio_as_the_user_types(editor, root) -> None:
    editor._constant_vars["poisson_ratio"].set("0.7")
    root.update()

    assert "-1 < nu < 0.5" in editor.status_text
    assert editor._derived.cget("text") == ""
    assert editor.spec is None


def test_editor_reports_incomplete_input_without_raising(editor, root) -> None:
    editor._constant_vars["elastic_modulus"].set("")
    root.update()

    assert "incomplete input" in editor.status_text
    assert editor.spec is None


def test_switching_to_orthotropic_rebuilds_the_form(editor, root) -> None:
    editor._symmetry.set("orthotropic")
    editor._rebuild_constant_fields()
    root.update()

    assert set(editor._constant_vars) == {
        "elastic_modulus_1",
        "elastic_modulus_2",
        "elastic_modulus_3",
        "poisson_ratio_12",
        "poisson_ratio_13",
        "poisson_ratio_23",
        "shear_modulus_12",
        "shear_modulus_13",
        "shear_modulus_23",
    }
    assert "valid orthotropic material" in editor.status_text

    # Individually plausible ratios that jointly describe an impossible
    # material: the reason validation runs on the assembled compliance.
    editor._constant_vars["poisson_ratio_12"].set("4.0")
    root.update()
    assert "positive definite" in editor.status_text


def test_dnv_hardening_produces_the_tabulated_curve(editor, root) -> None:
    editor._hardening_kind.set("dnv_c208")
    editor._rebuild_hardening_fields()
    editor._grade.set("S420")
    editor._hardening_vars["thickness"].set("20")
    root.update()

    spec = editor.spec
    assert spec is not None
    assert spec.hardening == {"kind": "dnv_c208", "grade": "S420", "thickness": 0.020}
    assert spec.hardening_curve() == dnv_c208_steel_curve("S420", 0.020)


def test_form_units_are_converted_to_si(editor, root) -> None:
    editor._constant_vars["elastic_modulus"].set("70")
    editor._yield_stress.set("240")
    root.update()

    spec = editor.spec
    assert spec is not None
    # Entered as 70 GPa and 240 MPa, stored as Pa.
    assert spec.constants["elastic_modulus"] == pytest.approx(70.0e9)
    assert spec.yield_stress == pytest.approx(240.0e6)


def test_a_material_survives_a_save_and_load_through_the_form(editor, root, tmp_path) -> None:
    editor._material_name.set("deck")
    editor._hardening_kind.set("linear")
    editor._rebuild_hardening_fields()
    editor._hardening_vars["sigma_yield"].set("355")
    editor._hardening_vars["hardening_modulus"].set("1500")
    root.update()

    original = editor.spec
    assert original is not None
    path = tmp_path / "deck.json"
    save_specs(path, [original])

    editor.write_spec(load_specs(path)[0])
    root.update()

    assert editor.spec == original


def test_an_unrepresentable_curve_is_reported_rather_than_silently_dropped(editor, root) -> None:
    spec = MaterialSpec(
        name="tabulated",
        constants={"elastic_modulus": 210.0e9, "poisson_ratio": 0.3},
        hardening={"kind": "piecewise_linear", "points": [[0.0, 355.0e6], [0.1, 420.0e6]]},
    )

    editor.write_spec(spec)
    root.update()

    # The form has no piecewise editor, so it says so instead of resetting the
    # material to elastic and losing the curve on the next save.
    assert "cannot edit" in editor.status_text
    assert editor._hardening_kind.get() == "none"


def test_the_library_pane_lists_every_shipped_material(editor, root) -> None:
    root.update()

    assert len(editor.library_names) == 19
    assert "S355 (t <= 16 mm)" in editor.library_names
    assert "EN AW-6082-T6" in editor.library_names


def test_selecting_a_library_material_shows_where_its_numbers_came_from(editor, root) -> None:
    editor._tree.selection_set("EN AW-6082-T6")
    root.update()

    text = editor._provenance.cget("text")
    assert "EN AW-6082-T6" in text
    assert "indicative" in text
    assert "thyssenkrupp" in text
    # An indicative entry says so on the entry itself.
    assert "NOT a design value" in text

    editor._tree.selection_set("S355 (t <= 16 mm)")
    root.update()
    tabulated = editor._provenance.cget("text")
    assert "DNV-RP-C208" in tabulated
    assert "NOT a design value" not in tabulated


def test_loading_a_library_material_fills_the_form(editor, root) -> None:
    editor._tree.selection_set("S460 (16 < t <= 40 mm)")
    editor.load_selected()
    root.update()

    spec = editor.spec
    assert spec is not None
    assert spec.name == "S460 (16 < t <= 40 mm)"
    assert editor._hardening_kind.get() == "dnv_c208"
    assert editor._grade.get() == "S460"
    assert spec.hardening_curve() == dnv_c208_steel_curve("S460", 0.028)
    assert "valid isotropic material" in editor.status_text


def test_the_plot_compares_the_edited_material_with_the_selection(editor, root) -> None:
    editor._hardening_kind.set("dnv_c208")
    editor._rebuild_hardening_fields()
    root.update()
    assert len(editor._plot_series()) == 1

    editor._tree.selection_set("S235 (t <= 16 mm)", "S460 (t <= 16 mm)")
    root.update()

    # The edited material first, then the library selection, so a new material is
    # seen against the grades it is meant to sit near.
    series = editor._plot_series()
    assert len(series) == 3
    assert series[0].label == editor.spec.name
    assert {item.label for item in series[1:]} == {"S235 (t <= 16 mm)", "S460 (t <= 16 mm)"}


def test_elastic_library_materials_contribute_no_curve(editor, root) -> None:
    editor._hardening_kind.set("none")
    editor._rebuild_hardening_fields()
    editor._tree.selection_set("EN AW-6082-T6")
    root.update()

    assert editor._plot_series() == []


def test_filtering_the_library_pane(editor, root) -> None:
    editor._search.set("S420")
    root.update()
    assert len(editor.library_names) == 3

    editor._search.set("")
    editor._only_nonlinear.set(True)
    editor._refresh_library_tree()
    root.update()
    assert len(editor.library_names) == 17
    assert "EN AW-6082-T6" not in editor.library_names


def test_adding_the_edited_material_to_the_library(editor, root, monkeypatch, user_library) -> None:
    from tkinter import messagebox, simpledialog

    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "yard steel")
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)

    editor._material_name.set("Yard plate")
    root.update()
    editor.add_current_to_library()
    root.update()

    assert user_library.is_file()
    assert "Yard plate" in editor.library_names
    entry = editor._library.get("Yard plate")
    assert entry.status == "user"
    assert entry.category == "yard steel"


def test_exporting_the_plotted_curves_to_svg(editor, root, monkeypatch, tmp_path) -> None:
    from tkinter import filedialog

    output = tmp_path / "from_gui.svg"
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda *a, **k: str(output))

    editor._tree.selection_set("S355 (t <= 16 mm)")
    root.update()
    editor.export_svg()

    assert output.is_file()
    assert "<polyline" in output.read_text(encoding="utf-8")


def test_the_editor_tears_down_cleanly(root) -> None:
    # Widget attributes that collide with tkinter's own internals only fail on
    # destroy, and only sometimes, so the teardown path is asserted directly.
    from anymaterial.gui import MaterialEditor

    frame = MaterialEditor(root)
    frame.pack(fill="both", expand=True)
    root.update()
    frame.destroy()
    root.update()

    assert not frame.winfo_exists()
