"""Structural material models for finite-element analysis.

The package owns material behaviour and nothing else: elastic symmetry and
compliance, the reductions a shell or beam formulation needs, nonlinear
hardening curves, directional yield criteria, and a serializable
specification.  Meshes, sections and solvers live elsewhere.

Elastic compliance uses engineering Voigt order ``[11, 22, 33, 23, 13, 12]``:

``[eps11, eps22, eps33, gamma23, gamma13, gamma12] = S @
  [sig11, sig22, sig33, tau23, tau13, tau12]``

This ordering is the family-wide convention.  It is stated here because this
package defines it, and every consumer is expected to match it rather than
transposing at the boundary.

The package deliberately does not import ANYsolver.  Materials are described
here and consumed there, never the other way round, so the dependency stays
acyclic and a material can be validated without a solver present.

``anymaterial.gui`` is not imported here, so importing the package never
requires a display or a tkinter build.
"""

from __future__ import annotations

from .contract import (
    ENGINEERING_VOIGT_ORDER,
    SUPPORTED_ELASTIC_SYMMETRIES,
    StructuralMaterial,
    elastic_compliance_matrix,
    is_isotropic_material,
    is_orthotropic_material,
    material_symmetry,
)
from .curves import (
    DNVC208MaterialCurve,
    HardeningCurve,
    LinearHardeningCurve,
    PiecewiseLinearCurve,
    PowerLawHardeningCurve,
    curve_from_properties,
)
from .isotropic import IsotropicMaterial
from .library import (
    STEEL_DENSITY,
    STEEL_POISSON_RATIO,
    LibraryEntry,
    MaterialLibrary,
    add_to_user_library,
    available_grades,
    builtin_library,
    dnv_c208_steel_curve,
    dnv_c208_steel_properties,
    library,
    steel,
    thickness_classes,
    user_library_path,
)
from .plot import CurveSeries, curve_svg, sample_curve, write_curve_svg
from .orthotropic import OrthotropicMaterial
from .reductions import (
    BeamMaterialProperties,
    beam_material_properties,
    shell_characteristic_modulus,
    shell_material_matrices,
)
from .spec import (
    MaterialSpec,
    build_hardening_curve,
    hardening_descriptor,
    load_specs,
    save_specs,
    spec_from_material,
)
from .validation import material_validation_errors, validate_material
from .yield_criteria import (
    Hill48Yield,
    hill48_coefficients,
    hill48_equivalent_stress,
    hill48_strengths,
)

__version__ = "0.2.0"

__all__ = [
    "BeamMaterialProperties",
    "CurveSeries",
    "DNVC208MaterialCurve",
    "ENGINEERING_VOIGT_ORDER",
    "HardeningCurve",
    "Hill48Yield",
    "IsotropicMaterial",
    "LibraryEntry",
    "LinearHardeningCurve",
    "MaterialLibrary",
    "MaterialSpec",
    "OrthotropicMaterial",
    "PiecewiseLinearCurve",
    "PowerLawHardeningCurve",
    "STEEL_DENSITY",
    "STEEL_POISSON_RATIO",
    "SUPPORTED_ELASTIC_SYMMETRIES",
    "StructuralMaterial",
    "add_to_user_library",
    "available_grades",
    "beam_material_properties",
    "build_hardening_curve",
    "builtin_library",
    "curve_from_properties",
    "curve_svg",
    "dnv_c208_steel_curve",
    "dnv_c208_steel_properties",
    "elastic_compliance_matrix",
    "hardening_descriptor",
    "hill48_coefficients",
    "hill48_equivalent_stress",
    "hill48_strengths",
    "is_isotropic_material",
    "is_orthotropic_material",
    "library",
    "load_specs",
    "material_symmetry",
    "material_validation_errors",
    "sample_curve",
    "save_specs",
    "shell_characteristic_modulus",
    "shell_material_matrices",
    "spec_from_material",
    "steel",
    "thickness_classes",
    "user_library_path",
    "validate_material",
    "write_curve_svg",
]
