# Bundled data sources

This inventory describes the two JSON assets distributed with ANYmaterial.
Per-record names, URLs, standards, warnings, calculations, and measurement
citations remain embedded in `materials.json` and are authoritative when more
specific than this summary.

## `dnv_rp_c208.json`

- **Source:** DNV-RP-C208, September 2019, amended October 2022, section 4.6.6.
- **Content:** low-fractile true stress-strain parameters for 17 grade and
  thickness rows covering S235, S275, S355, S420, and S460.
- **Recorded:** 2026-07-30 from the cited edition.
- **Units:** stress and moduli are stored in MPa, thickness in mm, and strain is
  dimensionless; `anymaterial.library` converts them to SI at the API boundary.
- **Processing:** the source table was transcribed into a project-authored JSON
  schema. No standards prose, figures, or pages are reproduced.
- **Assumptions:** `default_eps_p_y1` is explicit in the file. Unsupported
  grades, thicknesses, and unlisted mean curves fail closed rather than being
  extrapolated.
- **Redistribution basis:** the file contains extracted numerical parameters
  and original structure, not a copy of the DNV publication. DNV retains all
  rights in its publication; users need access to the governing edition and
  must comply with its terms. ANYmaterial grants no license to DNV content.

## `materials.json`

- **Sources:** Aluminum Association references; EN-oriented supplier and design
  publications; Ductile Iron Society data; the NCAMP/NIAR Hexcel 8552 IM7
  qualification programme; and Hartloper, Ozden, de Castro e Sousa & Lignos,
  *Database of Uniaxial Cyclic and Tensile Coupon Tests for Structural Metallic
  Materials*, v1.0.0, https://doi.org/10.5281/zenodo.6965147.
- **Content:** nine indicative entries and seven measured-mean entries. Every
  entry carries a source, status, standard or campaign, and warnings where the
  value is not a characteristic or design value.
- **Recorded:** initial compilation 2026-07-30; source review and measured-data
  update 2026-07-31.
- **Units:** stored values are SI: Pa, kg/m3, metres, and dimensionless strain.
- **Processing:** project-authored normalization maps heterogeneous sources to
  the `anymaterial.library` schema. The six Zenodo campaign records are means of
  named coupon sets; their engineering stress-strain data were converted to true
  stress and true plastic strain as recorded in each entry. The NCAMP/NIAR entry
  identifies measured constants separately from transverse-isotropy and
  Poisson-ratio assumptions.
- **Assumptions:** conventional elastic constants, curve forms, conversions,
  inferred constants, and design-value caveats are recorded per entry. Missing
  support is not silently filled.
- **Redistribution basis:** the six Zenodo-derived records are attributed and
  redistributed under their stated `CC-BY-4.0` source license. The
  project-authored compilation and annotations are CC BY 4.0 under
  `LICENSE_DATA.md`. All other source values retain their source-specific terms;
  no standards or manufacturer publications are bundled or relicensed.
