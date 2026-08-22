# Changelog

## Unreleased

Added:

- **Ecosystem governance.** The canonical `ECOSYSTEM_GUIDE.md` records domain
  ownership, compatibility, qualification and patch-only release rules shared
  by the ANY repositories.

Changed:

- **Safer publication.** The Trusted Publishing workflow now checks metadata
  and artifact contents, installs and smoke-tests the built wheel, rejects a
  mismatched release tag, blocks prerelease publication and limits OIDC to the
  publishing jobs. `RELEASING.md` records the TestPyPI and production procedure.
- **Concurrent test isolation.** Each pytest run receives a unique repository-
  local temporary directory, and tests that create a real Tk window are opt-in
  through `ANYMATERIAL_RUN_GUI_TESTS=1`. Windows CI opts in so the full editor
  suite remains a required release gate.
- **Current GitHub Actions runtime.** Checkout and Python setup use their Node
  24-based v7 actions, removing the Node 20 deprecation from CI and publication.

## 0.1.0 - 2026-08-20

First public feature release. The material code is extracted from ANYsolver and
ANYfem; see [MIGRATION.md](MIGRATION.md) for provenance.

Added:

- **Embeddable material selection.** `MaterialEditor(on_apply=...)` adds a
  **Use material** button, and `open_material_editor` opens the same validated
  editor inside an application's existing Tk event loop.
- **A material library.** `library()` returns 33 named materials, including the
  17 DNV-RP-C208 grade and thickness-class rows, curated cited entries, and
  measured campaign means. `MaterialLibrary` supports `get`, `find` (by category, status,
  text or whether it has a curve), `add`, `remove` and JSON round-tripping;
  `LibraryEntry` carries the category, the standard, the source and free notes.
- **Provenance as a first-class field.** Every entry has a `status`:
  `tabulated` for a standard's own table, `indicative` for a typical published
  figure that is **not a design value**, `user` for anything added at runtime.
  `LibraryEntry.is_design_value` exposes the distinction, and the CLI and the
  editor both surface it.
- **User-extensible.** `add_to_user_library` writes to
  `~/.anymaterial/materials.json`, or wherever `ANYMATERIAL_LIBRARY` points. A
  user entry with the same name as a shipped one takes precedence, which is how a
  grade gets corrected locally without editing the package. Anything added is
  recorded as `status="user"` even if it claims otherwise, so adding cannot
  launder provenance.
- **Curve plots as SVG.** `anymaterial.plot` renders flow curves without a
  plotting dependency — hand-written SVG, so the output goes into a report or a
  commit as text. `sample_curve`, `curve_svg` and `write_curve_svg`.
- **CLI** gained `library` (list and filter), `plot` (write an SVG) and `add`
  (put a material in the user library).
- **Editor** gained a library pane: browse and filter on the left, load an entry
  into the form, see the selected entry's provenance, and plot the edited
  material against the library selection. Buttons add the current material to the
  library and export the plotted curves to SVG.

**The shipped library is 33 materials.** It grew from 19 with a supplied
candidate set, then shrank again when the citations were checked: seven entries
were removed because their cited source does not support their numbers.

**One composite is back, properly sourced.** `IM7/8552 UD lamina, RTD (measured
mean)` uses room-temperature-dry campaign means from the
[NCAMP/NIAR Hexcel 8552 IM7 unidirectional qualification programme](https://www.wichita.edu/industry_and_defense/NIAR/Research/hexcel8552.php),
generated under FAA oversight — E1 23.51 Msi, E2 1.30 Msi, G12 0.68 Msi,
nu12 0.316, read from data report CAM-RP-2009-015 Rev A sections 2.3.1/2.3.2/2.3.5
with the environmental column resolved as RTD (70 °F, dry). The remaining five
constants are **not measured**: E3, nu13 and G13 follow from assumed transverse
isotropy, nu23 is assumed 0.45 outright, and G23 follows exactly from those. The
`calculation` record says which is which. Internal check: nu21 by reciprocity is
0.0175 against the programme's separately measured transverse-compression nu21 of
0.024. It carries no yield stress and defines no failure criterion.

Added `run_gui.py` at the repository root — an entry point for an IDE's Run
button that puts `src` on `sys.path` first, so the editor opens from a bare
checkout with nothing installed, and what runs is the working tree rather than an
installed copy. There is a test that executes it.

Added a new status, **`measured`**, and six entries under it from the
[Zenodo coupon database](https://doi.org/10.5281/zenodo.6965147) (Hartloper,
Ozden, de Castro e Sousa & Lignos 2022, v1.0.0, **CC-BY-4.0**): S235/275 JR+AR
15 mm plate, S355 J2+N 15 mm plate, S355 J2+M IPE270 flange, S460 NL 25 mm plate,
S690 QL 12 mm plate and A992 Gr.50 W14X82 flange. Each is the mean of a named
campaign and carries its coupon count, the coefficient of variation on both yield
and modulus, the product form, the campaign citekey, the licence and the full
citation.

A `measured` entry is **not** a design value and says so loudly: the measured
mean yield of S355 is 412 MPa against 357 MPa tabulated, so using a mean as a
design strength is unconservative. `LibraryEntry` refuses `status="measured"`
without a measurement record — a measured value without its sample size and
scatter is a number claiming an authority it cannot show.

Removed, each after checking the cited source:

| Entry | Why |
| --- | --- |
| T300/5208 UD lamina | cited NASA report is *Space Radiation Effects on Graphite-Epoxy* and covers T300/**934** |
| E-glass/epoxy UD lamina | cited NASA report is *Thermal expansion properties of composite materials* |
| IM7/8552 UD lamina | the entry's own notes admitted the citation does not source its elastic constants |
| Norway spruce | Poisson ratios 0.37/0.47/0.44 are the Wood Handbook's **Sitka** spruce row, and the moduli match neither species |
| Titanium Grade 2 | cited TIMET datasheet URL returns HTTP 404 |
| Ti-6Al-4V Grade 5 | cited TIMET datasheet URL returns HTTP 404 |
| EN AW-6082-T6 extrusion | cited hydro.com URL returns HTTP 404, and a verified 6082-T6 entry already ships |

Re-sourced rather than removed:

- **EN AW-5083-H116** — dead hydro.com link replaced; the 215 MPa proof is
  confirmed as the EN 485-2 minimum for the temper.
- **AA 6061-T6, AA 7075-T6** — no longer cite a licensed table as if it were the
  source; the notes now say plainly that these are widely corroborated typical
  values and that the authoritative minimums are elsewhere.
- **The three nonlinear stainless/duplex curves** — the notes now separate what
  the source supports (the Ramberg-Osgood form per EN 1993-1-4 Annex C, and the
  fy/fu inputs) from what was computed here (the tabulated points).

Everything that survived was validated before merging: it builds, its compliance
is symmetric and positive definite, and every flow curve is finite, monotonic and
has a non-negative hardening modulus.

- `LibraryEntry` gained **`calculation`** (how a derived entry was derived — the
  Ramberg-Osgood exponent behind a tabulated curve) and **`measurement`** (coupon
  count, scatter, campaign, licence, citation). Without the first, the candidate
  set's derivation records would have been silently dropped on import.
- A test now fails the build if any shipped entry lacks a source, a standard or
  notes.
- `anymaterial library` prints only the warning matching the statuses actually
  listed, so it stays worth reading, and takes `--status measured`. The choices
  are derived from the library's own status list so the two cannot drift.
- `anymaterial library` sizes its name column to the content, because a fixed
  width truncated the longer alloy names into ambiguity.

The first two curated materials were added from sources found online. Their
numbers are attributed in `data/materials.json` and marked `indicative`:

- **EN AW-6082-T6** — E 70 GPa, 0.2% proof 310 MPa, tensile 340 MPa, density
  2700 kg/m³, from the thyssenkrupp datasheet. That datasheet does not separate
  tempers, and EN 1999-1-1 characteristic values for design are lower and depend
  on product form and thickness; the entry says so.
- **EN 1.4404 (316L)** — E 200 GPa and density 8000 kg/m³ from the thyssenkrupp
  datasheet, 0.2% proof 220 MPa and tensile 500 MPa as commonly quoted for the
  grade under EN 10088-3.

Neither carries a hardening curve, because no citable source for one was found.
Nothing was invented to fill the gap: an aluminium entry (EN AW-5083-H111) was
prepared and then dropped when both candidate sources returned HTTP 403 and the
numbers could not be verified.

### Initial package foundation

Added:

- **Contract** — `StructuralMaterial` protocol, `ENGINEERING_VOIGT_ORDER`,
  symmetry resolution and `elastic_compliance_matrix`. Structural rather than
  inheritance-based, so a material defined in another package satisfies it
  without importing anything from here.
- **Materials** — `IsotropicMaterial` and `OrthotropicMaterial`, both validated
  on construction.
- **Reductions** — `shell_material_matrices`, `beam_material_properties` and
  `shell_characteristic_modulus`, all derived from the 6x6 compliance so
  isotropic and orthotropic materials reach a formulation by the same path.
- **Yield** — `Hill48Yield` plus free functions `hill48_strengths`,
  `hill48_coefficients` and `hill48_equivalent_stress` that consume the
  six-strength protocol by attribute lookup.
- **Curves** — the `HardeningCurve` protocol and four implementations:
  `LinearHardeningCurve`, `PiecewiseLinearCurve`, `PowerLawHardeningCurve` and
  the ported `DNVC208MaterialCurve`. The first three are new.
- **Library** — `steel()`, `available_grades()`, `thickness_classes()`,
  `dnv_c208_steel_properties()` and `dnv_c208_steel_curve()`. The RP-C208 grade
  table now lives in `data/dnv_rp_c208.json` instead of in code.
- **Specifications** — `MaterialSpec`, which records *how to rebuild* a
  hardening curve rather than a frozen copy, so a saved material does not reload
  as elastic. `hardening_descriptor` raises for a curve it cannot describe rather
  than serializing it away.
- **Editor** — a tkinter form with live validation and a flow-curve plot on a
  plain `Canvas`, entry point `anymaterial-gui`.
- **CLI** — `anymaterial grades|properties|curve|show|validate`, each with
  `--json`.

Verified bit-exact against `anysolver` 0.1.3 at
`8b4553cc680ff925df850e627165fc336615eaba` for the full RP-C208 table (17 rows),
the flow stress and hardening modulus of every resulting curve, isotropic and
orthotropic compliance, all three reductions, the Hill-48 coefficients,
quadratic form, utilization and equivalent stress, and the exact wording of
every validation message.

Deliberate differences from the source, both to be confirmed when ANYsolver is
stripped:

- `IsotropicMaterial` validates on construction. `anysolver.fe_core.Material`
  does not, so a caller that built a material with an inadmissible Poisson ratio
  and never used it would now fail at construction instead of at first use.
- Ramberg-Osgood is not implemented. It has no distinct yield point, so as a
  flow curve its stress tends to zero as plastic strain does, which a return
  mapping cannot use; the usual repairs produce a different curve while keeping
  the name. `PowerLawHardeningCurve.from_yield` covers the same behaviour with an
  explicit yield stress.

Not included, and staying in ANYsolver: `FiberSectionPlasticityConfig` (a solver
fiber grid, not a material) and all section properties.

## 0.0.1

- Repository scaffolding: packaging metadata, CI across Python 3.11-3.14 on
  Windows and Linux, and the layering checks that keep the package a leaf of the
  dependency graph.
