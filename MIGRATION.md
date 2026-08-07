# Migration to ANYmaterial

ANYmaterial is a curated extraction, not a filtered-history import, following
the precedent set by `ANYsolver/MIGRATION.md`.

## Provenance

- Material contract, orthotropic elasticity, Hill-48 yield and the shell/beam
  reductions: `audunarn/ANYsolver` `src/anysolver/materials.py`, at
  `8b4553cc680ff925df850e627165fc336615eaba` (branch `extract_mat_mesh_io`).
- Nonlinear hardening curves and the DNV-RP-C208 section 4.6.6 low-fractile
  steel table: `audunarn/ANYsolver` `src/anysolver/material_curves.py`, same
  commit.
- The isotropic material record: `audunarn/ANYsolver`
  `src/anysolver/fe_core.py` (`Material`), same commit.
- The serializable material specification, including hardening recorded as
  *how to rebuild the curve* rather than a frozen curve object:
  `audunarn/ANYfem` `src/anyfem/model/materials.py`, at
  `245b82ec68496fde1f8880c6a360f69973208bca` (branch `main`).

## Included

- Elastic symmetry declaration, validated 6x6 engineering compliance, and the
  isotropic/orthotropic material records.
- Shell plane-stress and transverse-shear reductions, beam local-axis constants,
  and the shell characteristic modulus used for numerical scaling.
- Hill-48 directional yield strengths and their quadratic form.
- Flow curves as a function of equivalent plastic strain, including the
  DNV-RP-C208 low-fractile steel curves, with the grade table moved from code
  into a data file.
- Material validation, serialization, a tkinter editor and a CLI.

## Verified equivalence

Checked against `anysolver` 0.1.3 at the provenance commit above, with both
packages importable at once. Bit-exact, not merely close:

- All 17 RP-C208 table rows across the five grades, every returned field
  including the `source` and `thickness_class` strings.
- `flow_stress` and `hardening_modulus` of the resulting curve for each row,
  sampled over 97 plastic strains spanning all three curve parts.
- Isotropic compliance and all three reductions over `E` in {70, 210} GPa and
  `nu` in {0.0, 0.3, 0.49}.
- Orthotropic compliance, reductions and the three derived Poisson ratios.
- Hill-48 coefficients, quadratic form, plane-stress form, utilization and
  equivalent stress over 50 random stress states, through both the class methods
  and the free functions.
- The exact wording of every validation message.

The permanent parity gate lives in ANYsolver, because ANYmaterial cannot import
it.

## Deliberate behavioural differences

Both were reviewed during the coordinated strip:

- **`IsotropicMaterial` validates on construction.** `anysolver.fe_core.Material`
  does not. `OrthotropicMaterial` always did, so this makes the two consistent,
  but a caller that constructed an inadmissible isotropic material and never used
  it now fails earlier. `FEModel.add_material` is the surface to check.
- **Ramberg-Osgood is not implemented.** It has no distinct yield point: as a
  flow curve its stress tends to zero as plastic strain does, which a return
  mapping cannot use, and the usual repairs produce a different curve while
  keeping the name. `PowerLawHardeningCurve.from_yield` covers the same behaviour
  with an explicit yield stress. `LinearHardeningCurve` was added instead, since
  bilinear plasticity is the more common engineering idealization and was missing
  entirely.

## Excluded

- `FiberSectionPlasticityConfig`, currently in `anysolver/material_curves.py`.
  It describes a solver fiber grid (`num_y`, `num_z`) rather than a material,
  and stays in ANYsolver.
- Section properties: `anysolver/sections.py`, `beam_sections.py` and
  `shell_sections.py`. A section is geometry, not material.
- Return mapping, consistent tangents and every other constitutive *integration*
  concern. ANYmaterial describes behaviour; the solver integrates it.
- RP-C208 mean curves. The source refuses to guess them and so does this
  package; supply explicit curve properties instead.

## Import changes

Applied in ANYsolver 0.2. ANYmaterial is now authoritative for these
implementations; ANYsolver retains compatibility facades only.

| Previous import | Replacement |
| --- | --- |
| `anysolver.materials` | `anymaterial` |
| `anysolver.material_curves` | `anymaterial.curves` |
| `anysolver.fe_core.Material` | `anymaterial.IsotropicMaterial` |
| `anyfem.model.materials.Material` | `anymaterial.MaterialSpec` |

ANYsolver re-exports the old names through its `0.2.x` line with a
`DeprecationWarning`.
