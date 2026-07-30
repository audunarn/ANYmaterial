"""The command line interface.

Exercised through ``main(argv)`` rather than a subprocess, so a failure points at
the line that raised.  Exit codes are part of the contract: a script that pipes
``--json`` output needs an invalid material to be distinguishable from a valid
one without parsing the text.
"""

from __future__ import annotations

import json

import pytest

from anymaterial import MaterialSpec, save_specs
from anymaterial.__main__ import main


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def _json_run(capsys, *argv: str) -> tuple[int, object]:
    code, out = _run(capsys, *argv)
    return code, json.loads(out)


def test_grades_lists_every_grade_and_class(capsys) -> None:
    code, payload = _json_run(capsys, "--json", "grades")

    assert code == 0
    assert set(payload) == {"S235", "S275", "S355", "S420", "S460"}
    assert payload["S355"][0] == "t <= 16"


def test_properties_reports_one_row_in_si_units(capsys) -> None:
    code, payload = _json_run(capsys, "--json", "properties", "S355", "0.010")

    assert code == 0
    assert payload["grade"] == "S355"
    assert payload["thickness_class"] == "t <= 16"
    assert payload["sigma_yield"] == pytest.approx(357.0e6)
    assert payload["E_pa"] == pytest.approx(210.0e9)


def test_properties_accepts_an_explicit_thickness_class(capsys) -> None:
    code, payload = _json_run(
        capsys, "--json", "properties", "S355", "0.200", "--thickness-class", "40 < t <= 63"
    )

    assert code == 0
    assert payload["sigma_yield"] == pytest.approx(336.9e6)


def test_properties_text_output_is_human_readable(capsys) -> None:
    code, out = _run(capsys, "properties", "S460", "0.010")

    assert code == 0
    assert "S460" in out
    assert "MPa" in out
    assert "GPa" in out


def test_curve_samples_the_flow_curve(capsys) -> None:
    code, payload = _json_run(capsys, "--json", "curve", "S355", "0.010", "--points", "5")

    assert code == 0
    assert len(payload["plastic_strain"]) == 5
    assert payload["flow_stress_pa"][0] == pytest.approx(320.0e6)
    assert payload["flow_stress_pa"][-1] > payload["flow_stress_pa"][0]
    assert payload["parameters"]["n"] == pytest.approx(0.166)


def test_show_summarizes_a_material_file(capsys, tmp_path) -> None:
    path = tmp_path / "m.json"
    save_specs(
        path,
        [
            MaterialSpec(
                name="deck",
                constants={"elastic_modulus": 210.0e9, "poisson_ratio": 0.3},
                density=7850.0,
                yield_stress=355.0e6,
                hardening={"kind": "dnv_c208", "grade": "S355", "thickness": 0.02},
            )
        ],
    )

    code, payload = _json_run(capsys, "--json", "show", str(path))

    assert code == 0
    summary = payload["materials"][0]
    assert summary["name"] == "deck"
    assert summary["nonlinear"] is True
    assert summary["beam"]["axial_modulus"] == pytest.approx(210.0e9)
    assert summary["shell_drilling_shear"] == pytest.approx(210.0e9 / 2.6)


def test_validate_reports_ok_and_exits_zero(capsys, tmp_path) -> None:
    path = tmp_path / "good.json"
    save_specs(
        path,
        [MaterialSpec(name="steel", constants={"elastic_modulus": 210.0e9, "poisson_ratio": 0.3})],
    )

    code, out = _run(capsys, "validate", str(path))

    assert code == 0
    assert "steel: ok" in out


def test_validate_exits_nonzero_for_an_inadmissible_material(capsys, tmp_path) -> None:
    # Written as raw JSON because MaterialSpec.build() is what must reject it;
    # the file itself is well formed, which is exactly the case validate exists
    # to catch.
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "materials": [
                    {
                        "name": "impossible",
                        "symmetry": "isotropic",
                        "constants": {"elastic_modulus": 210.0e9, "poisson_ratio": 0.7},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    code, payload = _json_run(capsys, "--json", "validate", str(path))

    assert code == 1
    assert payload["materials"][0]["valid"] is False
    assert payload["materials"][0]["errors"]


def test_usage_errors_exit_two_and_report_on_stderr(capsys) -> None:
    assert main(["properties", "S500", "0.010"]) == 2
    captured = capsys.readouterr()
    assert "Unsupported RP-C208 steel grade" in captured.err

    assert main(["properties", "S355", "0.5"]) == 2
    assert "outside the built-in RP-C208 range" in capsys.readouterr().err

    assert main(["show", "does-not-exist.json"]) == 2
    assert "error:" in capsys.readouterr().err


def test_a_missing_subcommand_is_a_parser_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


def test_library_lists_the_shipped_materials(capsys) -> None:
    code, payload = _json_run(capsys, "--json", "library")

    assert code == 0
    names = [item["name"] for item in payload["materials"]]
    assert len(names) == 19
    assert "S355 (t <= 16 mm)" in names
    assert "EN AW-6082-T6" in names
    assert payload["user_library"]


def test_library_filters(capsys) -> None:
    _code, aluminium = _json_run(capsys, "--json", "library", "--category", "aluminium")
    assert [item["name"] for item in aluminium["materials"]] == ["EN AW-6082-T6"]

    _code, nonlinear = _json_run(capsys, "--json", "library", "--nonlinear")
    assert len(nonlinear["materials"]) == 17

    _code, searched = _json_run(capsys, "--json", "library", "--search", "1.4404")
    assert [item["name"] for item in searched["materials"]] == ["EN 1.4404 (316L)"]

    _code, indicative = _json_run(capsys, "--json", "library", "--status", "indicative")
    assert len(indicative["materials"]) == 2


def test_library_text_output_warns_about_indicative_values(capsys) -> None:
    code, out = _run(capsys, "library", "--category", "aluminium")

    assert code == 0
    assert "EN AW-6082-T6" in out
    assert "indicative" in out
    # The whole risk is a looked-up number being used as a design value, so the
    # caveat is printed every time rather than left in a README.
    assert "not a design value" in out
    assert "governing standard" in out


def test_plot_writes_an_svg_with_one_curve_per_material(capsys, tmp_path) -> None:
    output = tmp_path / "curves.svg"
    code, payload = _json_run(
        capsys, "--json", "plot",
        "S235 (t <= 16 mm)", "S355 (t <= 16 mm)", "S460 (t <= 16 mm)",
        "-o", str(output),
    )

    assert code == 0
    assert payload["output"] == str(output)
    text = output.read_text(encoding="utf-8")
    assert text.count("<polyline") == 3
    assert "true plastic strain" in text


def test_plot_refuses_an_elastic_material_and_says_where_to_look(capsys) -> None:
    assert main(["plot", "EN AW-6082-T6", "-o", "x.svg"]) == 2
    captured = capsys.readouterr().err
    assert "is elastic and has no flow curve" in captured
    assert "--nonlinear" in captured


def test_plot_guards_overwriting(capsys, tmp_path) -> None:
    output = tmp_path / "curves.svg"
    assert main(["plot", "S355 (t <= 16 mm)", "-o", str(output)]) == 0
    assert main(["plot", "S355 (t <= 16 mm)", "-o", str(output)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert main(["plot", "S355 (t <= 16 mm)", "-o", str(output), "--overwrite"]) == 0


def test_add_puts_a_material_in_the_user_library(capsys, user_library) -> None:
    code, payload = _json_run(
        capsys, "--json", "add", "Yard plate",
        "--elastic-modulus", "210", "--yield-stress", "355",
        "--grade", "S355", "--thickness", "0.02",
        "--category", "structural steel", "--source", "mill certificate",
    )

    assert code == 0
    assert payload["added"] == "Yard plate"
    assert user_library.is_file()

    _code, listed = _json_run(capsys, "--json", "library", "--search", "Yard")
    entry = listed["materials"][0]
    assert entry["status"] == "user"
    assert entry["source"] == "mill certificate"
    assert entry["hardening"] == {"kind": "dnv_c208", "grade": "S355", "thickness": 0.02}

    # And it plots, because the descriptor rebuilds the curve.
    assert main(["plot", "Yard plate", "-o", str(user_library.parent / "y.svg")]) == 0


def test_add_supports_a_bilinear_curve_and_units_are_converted(capsys, user_library) -> None:
    assert main([
        "add", "Bilinear", "--elastic-modulus", "200", "--poisson-ratio", "0.29",
        "--density", "7800", "--yield-stress", "300", "--hardening-modulus", "1500",
    ]) == 0

    from anymaterial import library

    spec = library().get("Bilinear").spec
    # Entered as GPa and MPa, stored as Pa.
    assert spec.constants["elastic_modulus"] == pytest.approx(200.0e9)
    assert spec.constants["poisson_ratio"] == pytest.approx(0.29)
    assert spec.density == pytest.approx(7800.0)
    assert spec.hardening == {"kind": "linear", "sigma_yield": 300.0e6, "hardening_modulus": 1500.0e6}


def test_add_refuses_a_duplicate_and_an_inadmissible_material(capsys, user_library) -> None:
    assert main(["add", "Twice", "--elastic-modulus", "210"]) == 0
    assert main(["add", "Twice", "--elastic-modulus", "210"]) == 2
    assert "already in the library" in capsys.readouterr().err
    assert main(["add", "Twice", "--elastic-modulus", "70", "--replace"]) == 0

    assert main(["add", "Impossible", "--elastic-modulus", "210", "--poisson-ratio", "0.9"]) == 2
    assert "nu < 0.5" in capsys.readouterr().err
