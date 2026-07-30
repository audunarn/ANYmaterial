"""Command line interface.

``python -m anymaterial <command>``, or ``anymaterial <command>`` once
installed.  Every command takes ``--json`` for machine-readable output, so the
tool is usable from a script without parsing formatted text.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Sequence

import numpy as np

from .contract import elastic_compliance_matrix, material_symmetry
from .library import (
    STATUSES,
    LibraryEntry,
    add_to_user_library,
    available_grades,
    dnv_c208_steel_curve,
    dnv_c208_steel_properties,
    library,
    thickness_classes,
    user_library_path,
)
from .plot import sample_curve, write_curve_svg
from .reductions import beam_material_properties, shell_material_matrices
from .spec import MaterialSpec, load_specs
from .validation import material_validation_errors

__all__ = ["main"]


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=float))


def _command_grades(args: argparse.Namespace) -> int:
    payload = {grade: list(thickness_classes(grade)) for grade in available_grades()}
    if args.json:
        _print_json(payload)
        return 0
    print("DNV-RP-C208 low-fractile steel grades (thickness in mm):")
    for grade, classes in payload.items():
        print(f"  {grade}: {', '.join(classes)}")
    return 0


def _command_properties(args: argparse.Namespace) -> int:
    properties = dnv_c208_steel_properties(
        args.grade, args.thickness, thickness_class=args.thickness_class
    )
    if args.json:
        _print_json(properties)
        return 0
    print(f"{properties['grade']}  thickness {properties['thickness_mm']:g} mm  "
          f"class {properties['thickness_class']}")
    print(f"  source          {properties['source']}")
    print(f"  E               {float(properties['E_pa']) / 1.0e9:.1f} GPa")
    for key in ("sigma_prop", "sigma_yield", "sigma_yield_2", "K"):
        print(f"  {key:<15} {float(properties[key]) / 1.0e6:.1f} MPa")
    for key in ("eps_p_y1", "eps_p_y2", "n"):
        print(f"  {key:<15} {float(properties[key]):g}")
    return 0


def _command_curve(args: argparse.Namespace) -> int:
    curve = dnv_c208_steel_curve(args.grade, args.thickness)
    strains = np.linspace(0.0, float(args.max_strain), int(args.points))
    stresses = curve.flow_stress(strains)
    moduli = curve.hardening_modulus(strains)
    if args.json:
        _print_json(
            {
                "grade": args.grade.upper(),
                "thickness_m": float(args.thickness),
                "parameters": curve.as_dict(),
                "plastic_strain": [float(value) for value in strains],
                "flow_stress_pa": [float(value) for value in stresses],
                "hardening_modulus_pa": [float(value) for value in moduli],
            }
        )
        return 0
    print(f"{'eps_p':>10} {'sigma [MPa]':>14} {'H [MPa]':>14}")
    for strain, stress, modulus in zip(strains, stresses, moduli):
        print(f"{strain:>10.5f} {stress / 1.0e6:>14.2f} {modulus / 1.0e6:>14.2f}")
    return 0


def _describe(spec: MaterialSpec) -> Dict[str, Any]:
    """Summarize one specification, including its derived reductions."""

    material = spec.build()
    compliance = elastic_compliance_matrix(material)
    plane_stress, transverse_shear, drilling = shell_material_matrices(material)
    beam = beam_material_properties(material)
    return {
        "name": spec.name,
        "symmetry": material_symmetry(material),
        "density": float(spec.density),
        "yield_stress": float(spec.yield_stress),
        "nonlinear": spec.is_nonlinear,
        "hardening": dict(spec.hardening) if spec.hardening else None,
        "constants": dict(spec.constants),
        "compliance_diagonal": [float(value) for value in np.diag(compliance)],
        "shell_plane_stress": [[float(value) for value in row] for row in plane_stress],
        "shell_transverse_shear": [float(value) for value in np.diag(transverse_shear)],
        "shell_drilling_shear": float(drilling),
        "beam": {
            "axial_modulus": beam.axial_modulus,
            "shear_modulus_xy": beam.shear_modulus_xy,
            "shear_modulus_xz": beam.shear_modulus_xz,
        },
    }


def _command_library(args: argparse.Namespace) -> int:
    entries = library().find(
        category=args.category, status=args.status, text=args.search,
        nonlinear=True if args.nonlinear else None,
    )
    if args.json:
        _print_json({
            "user_library": str(user_library_path()),
            "materials": [entry.to_dict() for entry in entries],
        })
        return 0
    if not entries:
        print("no materials match")
        return 0
    # Sized to the content: a fixed width truncated the longer alloy names into
    # ambiguity, which is the one thing a material listing must not do.
    name_width = max(len("material"), *(len(entry.name) for entry in entries))
    category_width = max(len("category"), *(len(entry.category) for entry in entries))
    print(
        f"{'material':<{name_width}}  {'category':<{category_width}}  "
        f"{'status':<10}  {'yield':>9}  hardening"
    )
    for entry in entries:
        yield_mpa = f"{entry.spec.yield_stress / 1.0e6:.0f} MPa" if entry.spec.yield_stress else "-"
        hardening = entry.spec.hardening["kind"] if entry.spec.hardening else "elastic"
        print(
            f"{entry.name:<{name_width}}  {entry.category:<{category_width}}  "
            f"{entry.status:<10}  {yield_mpa:>9}  {hardening}"
        )
    print()
    print(f"user library: {user_library_path()}")
    # Said every time the list is printed, because the whole risk this library
    # carries is a looked-up number being used as a design value.  Only shown for
    # the statuses actually listed, so the warning stays worth reading.
    shown = {entry.status for entry in entries}
    if "measured" in shown:
        print("status 'measured' is the MEAN of a test campaign, NOT a characteristic value:")
        print("the mean yield exceeds the nominal, so using it as a design strength is")
        print("unconservative. Use it to validate a model against the tests it came from.")
    if "indicative" in shown:
        print("status 'indicative' means a typical published figure, not a design value:")
        print("check it against the governing standard or the mill certificate.")
    if shown <= {"tabulated"}:
        print("all listed materials are 'tabulated': reproduced from a standard's own table.")
    return 0


def _command_plot(args: argparse.Namespace) -> int:
    catalogue = library()
    series = []
    for name in args.materials:
        entry = catalogue.get(name)
        curve = entry.spec.hardening_curve()
        if curve is None:
            raise ValueError(
                f"{name!r} is elastic and has no flow curve to plot; "
                "list the nonlinear materials with `anymaterial library --nonlinear`"
            )
        series.append(sample_curve(curve, name, max_strain=args.max_strain, samples=args.points))

    path = write_curve_svg(
        args.output, series, overwrite=args.overwrite, title=args.title, stress_unit="MPa"
    )
    if args.json:
        _print_json({"output": str(path), "materials": list(args.materials)})
    else:
        print(f"wrote {path} ({len(series)} curve(s))")
    return 0


def _command_add(args: argparse.Namespace) -> int:
    hardening = None
    if args.grade:
        hardening = {"kind": "dnv_c208", "grade": args.grade, "thickness": args.thickness}
    elif args.hardening_modulus is not None:
        hardening = {
            "kind": "linear",
            "sigma_yield": args.yield_stress * 1.0e6,
            "hardening_modulus": args.hardening_modulus * 1.0e6,
        }

    entry = LibraryEntry(
        spec=MaterialSpec(
            name=args.name,
            symmetry="isotropic",
            constants={
                "elastic_modulus": args.elastic_modulus * 1.0e9,
                "poisson_ratio": args.poisson_ratio,
            },
            density=args.density,
            yield_stress=args.yield_stress * 1.0e6,
            hardening=hardening,
        ),
        category=args.category,
        status="user",
        standard=args.standard,
        source=args.source,
        notes=args.notes,
    )
    path = add_to_user_library(entry, replace_existing=args.replace)
    if args.json:
        _print_json({"added": entry.name, "library": str(path)})
    else:
        print(f"added {entry.name!r} to {path}")
    return 0


def _command_show(args: argparse.Namespace) -> int:
    summaries = [_describe(spec) for spec in load_specs(args.input)]
    if args.json:
        _print_json({"materials": summaries})
        return 0
    for summary in summaries:
        print(f"{summary['name']}  ({summary['symmetry']})")
        print(f"  density         {summary['density']:g} kg/m3")
        print(f"  yield stress    {summary['yield_stress'] / 1.0e6:g} MPa")
        print(f"  nonlinear       {summary['nonlinear']}")
        if summary["hardening"]:
            print(f"  hardening       {summary['hardening']}")
        for key, value in sorted(summary["constants"].items()):
            print(f"  {key:<15} {value:g}")
        print(f"  beam E          {summary['beam']['axial_modulus'] / 1.0e9:.2f} GPa")
        print(f"  drilling G      {summary['shell_drilling_shear'] / 1.0e9:.2f} GPa")
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    results: List[Dict[str, Any]] = []
    exit_code = 0
    for spec in load_specs(args.input):
        try:
            material = spec.build()
        except ValueError as error:
            results.append({"name": spec.name, "valid": False, "errors": [str(error)]})
            exit_code = 1
            continue
        errors = list(material_validation_errors(material))
        results.append({"name": spec.name, "valid": not errors, "errors": errors})
        if errors:
            exit_code = 1

    if args.json:
        _print_json({"materials": results})
        return exit_code
    for result in results:
        status = "ok" if result["valid"] else "INVALID"
        print(f"{result['name']}: {status}")
        for message in result["errors"]:
            print(f"  - {message}")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anymaterial", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("grades", help="list tabulated steel grades and thickness classes")

    catalogue = sub.add_parser("library", help="list the materials in the library")
    catalogue.add_argument("--category", help="filter by category, e.g. aluminium")
    # Derived from the library's own list, so the two cannot drift apart.
    catalogue.add_argument("--status", choices=STATUSES)
    catalogue.add_argument("--search", help="filter by name or category substring")
    catalogue.add_argument("--nonlinear", action="store_true", help="only materials with a flow curve")

    plot = sub.add_parser("plot", help="plot flow curves to an SVG file")
    plot.add_argument("materials", nargs="+", help="library material names")
    plot.add_argument("--output", "-o", default="flow_curves.svg")
    plot.add_argument("--title", default="Flow curves")
    plot.add_argument("--max-strain", type=float, default=0.10)
    plot.add_argument("--points", type=int, default=201)
    plot.add_argument("--overwrite", action="store_true")

    add = sub.add_parser("add", help="add an isotropic material to the user library")
    add.add_argument("name")
    add.add_argument("--elastic-modulus", type=float, required=True, help="E in GPa")
    add.add_argument("--poisson-ratio", type=float, default=0.3)
    add.add_argument("--density", type=float, default=7850.0, help="kg/m3")
    add.add_argument("--yield-stress", type=float, default=0.0, help="MPa")
    add.add_argument("--hardening-modulus", type=float, help="bilinear plastic modulus in MPa")
    add.add_argument("--grade", help="attach a DNV-RP-C208 curve for this grade instead")
    add.add_argument("--thickness", type=float, default=0.010, help="metres, with --grade")
    add.add_argument("--category", default="other")
    add.add_argument("--standard", help="the standard the numbers come from")
    add.add_argument("--source", help="where the numbers came from")
    add.add_argument("--notes")
    add.add_argument("--replace", action="store_true", help="overwrite a material of the same name")

    properties = sub.add_parser("properties", help="show one RP-C208 table row in SI units")
    properties.add_argument("grade")
    properties.add_argument("thickness", type=float, help="plate thickness in metres")
    properties.add_argument(
        "--thickness-class",
        default="auto",
        help="select a table row explicitly, e.g. '40 < t <= 63'",
    )

    curve = sub.add_parser("curve", help="sample a flow curve")
    curve.add_argument("grade")
    curve.add_argument("thickness", type=float, help="plate thickness in metres")
    curve.add_argument("--points", type=int, default=11)
    curve.add_argument("--max-strain", type=float, default=0.1)

    show = sub.add_parser("show", help="summarize materials in a JSON file")
    show.add_argument("input")

    validate = sub.add_parser("validate", help="validate materials in a JSON file")
    validate.add_argument("input")

    args = parser.parse_args(argv)
    handlers = {
        "grades": _command_grades,
        "library": _command_library,
        "plot": _command_plot,
        "add": _command_add,
        "properties": _command_properties,
        "curve": _command_curve,
        "show": _command_show,
        "validate": _command_validate,
    }
    try:
        return handlers[args.command](args)
    except (FileExistsError, FileNotFoundError, KeyError, NotImplementedError, ValueError) as error:
        # A bad grade, an out-of-range thickness or a malformed file is a usage
        # error, not a crash: report it on stderr and exit non-zero.
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
