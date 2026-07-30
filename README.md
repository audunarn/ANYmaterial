# ANYmaterial

Structural material models for finite-element analysis: isotropic and
orthotropic elasticity, nonlinear hardening curves, and directional yield
criteria, with a small tkinter editor and a command-line interface.

```powershell
python -m pip install ANYmaterial
```

The distribution is `ANYmaterial` and the import package is `anymaterial`.

## Quick start

```python
import anymaterial as am

# Browse the library.
catalogue = am.library()
catalogue.names                      # 19 shipped materials
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

19 materials ship with the package, and every one names where its numbers came
from:

| Materials | Status | Source |
| --- | --- | --- |
| S235, S275, S355, S420, S460 — 17 grade/thickness rows, each with its flow curve | `tabulated` | DNV-RP-C208 section 4.6.6, low fractile |
| EN AW-6082-T6 | `indicative` | [thyssenkrupp datasheet](https://www.thyssenkrupp-materials.co.uk/aluminium-6082.html) |
| EN 1.4404 (316L) | `indicative` | [thyssenkrupp datasheet](https://www.thyssenkrupp-materials.co.uk/stainless-steel-316l-14404.html) |

**`tabulated` means the numbers are a standard's own table**, reproduced with the
reference. **`indicative` means they are typical published figures and are not
design values**: a grade designation covers a range that varies with product
form, temper and thickness, and the governing standard or the mill certificate is
what settles it. The distinction is carried through the API, the CLI and the
editor rather than being left in a README, because a library that presents a
looked-up number and a qualified number identically invites the first to be used
as the second.

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
