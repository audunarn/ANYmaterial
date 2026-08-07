# ANYmaterial

Structural material models for finite-element analysis: isotropic and
orthotropic elasticity, nonlinear hardening curves, and directional yield
criteria, with a small tkinter editor and a command-line interface.

After the first package-index release, install with
`python -m pip install ANYmaterial`. Until then, use the editable development
setup below.

The distribution is `ANYmaterial` and the import package is `anymaterial`.

## Quick start

```python
import anymaterial as am

# Browse the library.
catalogue = am.library()
catalogue.names                      # 33 shipped materials
catalogue.find(category="aluminium")
catalogue.get("S355 (16 < t <= 40 mm)").build()

# Plot flow curves, with no plotting dependency.
am.write_curve_svg("curves.svg", [
    am.sample_curve(catalogue.get(name).spec.hardening_curve(), name)
    for name in ("S235 (t <= 16 mm)", "S355 (t <= 16 mm)", "S460 (t <= 16 mm)")
])

# Add your own, and it is there next time.
am.add_to_user_library(am.LibraryEntry(
    spec=am.MaterialSpec(
        name="Yard plate S355",
        constants={"elastic_modulus": 210e9, "poisson_ratio": 0.3},
        density=7850.0, yield_stress=362e6,
        hardening={"kind": "dnv_c208", "grade": "S355", "thickness": 0.02},
    ),
    category="structural steel",
    source="mill certificate 2026-07",
))

# A steel grade from the DNV-RP-C208 table, with its hardening curve.
plate = am.steel("S355", thickness=0.020, nonlinear=True)
plate.yield_stress          # 346.9e6 Pa, the 16 < t <= 40 row
plate.hardening_curve.flow_stress(0.05)

# What a shell formulation needs, derived from the compliance.
Q, transverse_shear, drilling = am.shell_material_matrices(plate)

# An orthotropic material with directional yield strengths.
ud = am.OrthotropicMaterial(
    "ud", 150e9, 10e9, 8e9, 0.25, 0.20, 0.30, 5e9, 4e9, 3e9,
    density=1600.0,
    hill_yield=am.Hill48Yield(400e6, 320e6, 280e6, 190e6, 175e6, 160e6),
)
am.beam_material_properties(ud).axial_modulus   # 150e9, not a fabricated E
```

Both are validated on construction, so an inadmissible combination of Poisson
ratios raises where it is entered rather than producing a stiffness matrix that
happens to be indefinite.

## The library

33 materials ship with the package, and every one names where its numbers came
from and what kind of number it is:

| Materials | Status | Source |
| --- | --- | --- |
| S235, S275, S355, S420, S460 — 17 grade/thickness rows, each with its flow curve | `tabulated` | DNV-RP-C208 §4.6.6, low fractile |
| S235/275, S355 (×2 product forms), S460, S690, A992 — campaign means with coupon counts and scatter | `measured` | [Zenodo coupon database](https://doi.org/10.5281/zenodo.6965147), CC-BY-4.0 |
| IM7/8552 carbon-epoxy UD lamina, room-temperature dry — orthotropic | `measured` | [NCAMP/NIAR Hexcel 8552 qualification](https://www.wichita.edu/industry_and_defense/NIAR/Research/hexcel8552.php) |
| EN AW-5083-H116, EN AW-6082-T6, AA 6061-T6, AA 7075-T6 | `indicative` | supplier and industry data |
| EN 1.4404 (316L) elastic + nonlinear, EN 1.4307 (304L) nonlinear, EN 1.4462 duplex nonlinear | `indicative` | EN 10088; curves derived per EN 1993-1-4 Annex C |
| EN-GJS-400-15 ductile iron | `indicative` | EN 1563 grade definition |

Three kinds of number, and **only the first is a design value**:

- **`tabulated`** — a standard's own table, reproduced with the reference.
- **`measured`** — the **mean** of a named test campaign. A mean is not a
  characteristic value: the measured mean yield of S355 is 412 MPa against a
  357 MPa tabulated value, so using it as a design strength is *unconservative*.
  It is here to validate a nonlinear model against the tests it came from. Each
  entry carries its coupon count and coefficient of variation.
- **`indicative`** — a typical published figure for the grade. A grade
  designation covers a range that varies with product form, temper and thickness.

The distinction is carried through the API (`LibraryEntry.is_design_value`), the
CLI (which prints the warning matching the statuses actually listed) and the
editor, because a library that presents all three identically invites the wrong
one to be used.

### Attribution

The `measured` entries come from Hartloper, A. R., Ozden, S., de Castro e Sousa,
A., & Lignos, D. G. (2022), *Database of Uniaxial Cyclic and Tensile Coupon Tests
for Structural Metallic Materials* (v1.0.0), Zenodo,
[doi:10.5281/zenodo.6965147](https://doi.org/10.5281/zenodo.6965147), licensed
**CC-BY-4.0**. Each entry records the originating campaign citekey so the
underlying experiments can be traced through the database's own reference list.

**`tabulated` means the numbers are a standard's own table**, reproduced with the
reference. **`indicative` means they are typical published figures and are not
design values**: a grade designation covers a range that varies with product
form, temper and thickness, and the governing standard or the mill certificate is
what settles it. The distinction is carried through the API, the CLI and the
editor rather than being left in a README, because a library that presents a
looked-up number and a qualified number identically invites the first to be used
as the second.

A **derived** entry also records *how* it was derived, in `LibraryEntry.calculation`
— the Ramberg-Osgood exponent behind a tabulated stainless curve, the
transverse-isotropy assumption behind a lamina's `G23`. A derived number whose
derivation is not recorded cannot be checked, and an assumption nobody can see is
one nobody will question.

Every shipped entry must name a source, a standard and its notes — there is a
test that fails the build if one does not. Entries whose cited source turned out
not to support their numbers have been removed rather than kept with a caveat;
see the changelog for which, and why.

**The one composite** is the IM7/8552 lamina, and it is careful about what it
claims: `E1`, `E2`, `G12` and `nu12` are room-temperature-dry campaign means from
the NCAMP qualification programme; `E3`, `nu13`, `G13`, `nu23` and `G23` are
**not measured** and follow from an assumed transverse isotropy, with `nu23 = 0.45`
assumed outright. `LibraryEntry.calculation` says exactly which is which. It
carries no yield stress and defines no failure criterion — composite failure is
not isotropic yielding, and strengths belong in the B-basis allowables report,
not here.

Materials you add go to `~/.anymaterial/materials.json`, or wherever
`ANYMATERIAL_LIBRARY` points — a project that wants its materials beside its
models can say so. A user entry with the same name as a shipped one wins, which
is how a grade gets corrected locally without editing the package.

## Command line

```bash
anymaterial library --nonlinear
```

```bash
anymaterial plot "S235 (t <= 16 mm)" "S355 (t <= 16 mm)" -o curves.svg
```

```bash
anymaterial add "Yard plate" --elastic-modulus 210 --yield-stress 362 --grade S355 --thickness 0.02 --source "mill cert 2026-07"
```

`library`, `plot`, `add`, `grades`, `properties`, `curve`, `show` and `validate`,
each with `--json`. `validate` exits non-zero when a material is inadmissible, so
it works as a check in a build.

`anymaterial-gui` opens the library and editor: browse and filter the materials
on the left, edit one in the middle, and on the right see the validation result,
the derived shell and beam properties, the provenance of the selected library
entry, and the flow curves — the material being edited plotted against whatever
is selected, so a new material is seen against the grades it should sit near.
Buttons load a library material into the form, add the current one to your
library, and export the plotted curves to SVG.

Applications can use the same editor as a real picker.  The optional callback
adds a **Use material** button and receives a validated `MaterialSpec`:

```python
from anymaterial.gui import open_material_editor

window, editor = open_material_editor(root, on_apply=material_dropdown.add)
```

This keeps material validation and unit conversion in ANYmaterial while the
host decides how its dropdown or project model stores the selected material.

## Scope

- **Elastic symmetry** — isotropic and orthotropic engineering materials, with a
  validated 6x6 compliance in Voigt order `[11, 22, 33, 23, 13, 12]`.
- **Reductions** — the plane-stress, transverse-shear and beam-axis constants a
  shell or beam formulation needs, computed from compliance rather than from
  re-entered engineering constants.
- **Nonlinear behaviour** — flow curves as a function of equivalent plastic
  strain: bilinear, tabulated, power law, and the DNV-RP-C208 section 4.6.6
  low-fractile steel curves.
- **Directional yield** — Hill-48 strengths in material axes, evaluated over a
  whole field of integration points at once.
- **Serialization** — a specification that survives a project-file round trip,
  recording *how to rebuild* its hardening curve rather than a frozen copy.
- **A library** — named materials in JSON, each carrying its category, its source
  and whether its numbers are a standard's table or a typical published figure,
  extensible at runtime.
- **Plots** — flow curves as standalone SVG, written by hand so that plotting
  costs no dependency.

Not in scope: section properties, meshes, elements, assembly or solution.
General anisotropy, laminates and ply failure are out of scope, and are refused
explicitly rather than approximated.

## Design notes

**Structural typing at the boundary.** A consumer needs a name, a density, a
declared elastic symmetry and an `elastic_compliance_matrix()`. Nothing has to
inherit from anything here, which is what lets a material cross a package
boundary — and why validation reads attributes rather than checking types.

**Vectorization is part of the curve contract.** `flow_stress` and
`hardening_modulus` accept and return numpy arrays of any shape, because a return
mapping calls them for every integration point and thickness layer at once.

**Failing closed.** Where the source material is silent this package raises
rather than extrapolating: a plate thickness outside a tabulated RP-C208 range is
an error, not an invitation to use the nearest row, and mean curves the
recommended practice does not tabulate are unavailable rather than interpolated.
An explicit `thickness_class` makes a documented deviation possible where an
accident is not.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layering, and
[MIGRATION.md](MIGRATION.md) for what was extracted from where.

## Units

SI throughout. Stresses and moduli in Pa, densities in kg/m³, lengths in m,
strains dimensionless. There is no conversion layer: a value that looks like MPa
is a bug, not a convention. The RP-C208 tables are tabulated in MPa in the source
document and converted once, at the data-file boundary. The editor accepts GPa and
MPa because that is how they are quoted on a drawing, and converts at the widget.

## Development

```powershell
python -m pip install -e "C:\Github\ANYmaterial[dev]"
python -m pytest
```

To open the editor straight from a checkout — including an IDE's Run button, with
nothing installed — run [`run_gui.py`](run_gui.py) at the repository root. It puts
`src` on `sys.path` first, so what runs is this working tree rather than an
installed copy.

```bash
python run_gui.py
```
