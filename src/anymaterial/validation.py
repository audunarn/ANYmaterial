"""Material contract validation.

Two entry points: :func:`material_validation_errors` collects every violation,
:func:`validate_material` raises on the first non-empty collection.  Collecting
rather than raising immediately is what lets an editor show a user everything
wrong with a material at once instead of one problem per attempt.

Validation is structural.  It reads attributes and never checks types, so a
material record defined in another package -- including one that never imported
this module -- is validated by exactly the same rules as one built here.
"""

from __future__ import annotations

from typing import Any, Tuple

import numpy as np

from .contract import (
    SUPPORTED_ELASTIC_SYMMETRIES,
    elastic_compliance_matrix,
    material_symmetry,
)
from .yield_criteria import Hill48Yield

__all__ = ["material_validation_errors", "validate_material"]


def _as_float(value: Any) -> float:
    """Coerce to float, mapping anything uncoercible onto NaN."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _compliance_errors(material: Any) -> list[str]:
    """Check that a compliance matrix is finite, symmetric and positive definite."""

    try:
        compliance = elastic_compliance_matrix(material)
    except Exception as exc:  # noqa: BLE001 - reported verbatim to the caller
        return [f"invalid elastic compliance: {exc}"]

    if not np.all(np.isfinite(compliance)):
        return ["elastic compliance matrix must contain only finite values"]

    # Symmetry is the reciprocal Poisson relation nu_ij/E_i == nu_ji/E_j.  The
    # tolerance is scaled by the matrix itself because compliance entries are
    # order 1/E: an absolute tolerance would be meaningless at 1e-11 Pa^-1.
    scale = max(float(np.max(np.abs(compliance))), np.finfo(float).tiny)
    if not np.allclose(compliance, compliance.T, rtol=1.0e-10, atol=scale * 1.0e-12):
        return ["elastic compliance matrix must be symmetric and obey reciprocal Poisson relations"]

    try:
        eigvals = np.linalg.eigvalsh(0.5 * (compliance + compliance.T))
    except np.linalg.LinAlgError as exc:
        return [f"elastic compliance eigensolution failed: {exc}"]
    if float(np.min(eigvals)) <= 0.0:
        # Positive definiteness is thermodynamic admissibility: a material that
        # releases strain energy under some load path is not a material.  It is
        # also what Poisson ratios entered independently most often violate.
        return ["elastic compliance matrix must be positive definite"]
    return []


def material_validation_errors(material: Any) -> Tuple[str, ...]:
    """Return deterministic structural-material contract violations."""

    errors: list[str] = []
    name = getattr(material, "name", None)
    if not isinstance(name, str) or not name.strip():
        errors.append("material name must be a non-empty string")

    try:
        symmetry = material_symmetry(material)
    except ValueError as exc:
        symmetry = ""
        errors.append(str(exc))
    if symmetry and symmetry not in SUPPORTED_ELASTIC_SYMMETRIES:
        if symmetry == "anisotropic":
            errors.append(
                "general anisotropic elasticity is not supported; use isotropic or orthotropic elasticity"
            )
        else:
            errors.append(
                f"elastic symmetry {symmetry!r} is not supported; use 'isotropic' or 'orthotropic'"
            )

    density = _as_float(getattr(material, "density", None))
    if not np.isfinite(density) or density < 0.0:
        errors.append("density must be finite and non-negative")

    if symmetry == "isotropic":
        E = getattr(material, "elastic_modulus", None)
        nu = getattr(material, "poisson_ratio", None)
        if E is not None:
            value = _as_float(E)
            if not np.isfinite(value) or value <= 0.0:
                errors.append("isotropic elastic modulus must be finite and positive")
        if nu is not None:
            value = _as_float(nu)
            if not np.isfinite(value) or not (-1.0 < value < 0.5):
                # nu == 0.5 is incompressible and makes the bulk modulus
                # infinite; nu <= -1 is thermodynamically inadmissible.
                errors.append("isotropic Poisson ratio must satisfy -1 < nu < 0.5")

    if symmetry == "orthotropic":
        for field_name in (
            "elastic_modulus_1",
            "elastic_modulus_2",
            "elastic_modulus_3",
            "shear_modulus_12",
            "shear_modulus_13",
            "shear_modulus_23",
        ):
            if hasattr(material, field_name):
                value = _as_float(getattr(material, field_name))
                if not np.isfinite(value) or value <= 0.0:
                    errors.append(f"{field_name} must be finite and positive")
        for field_name in ("poisson_ratio_12", "poisson_ratio_13", "poisson_ratio_23"):
            if hasattr(material, field_name):
                if not np.isfinite(_as_float(getattr(material, field_name))):
                    errors.append(f"{field_name} must be finite")
                # The admissible range for an orthotropic Poisson ratio depends
                # on the moduli, so it is not bounded here.  Positive
                # definiteness of the assembled compliance is the real test,
                # and it is applied below.

    if symmetry in SUPPORTED_ELASTIC_SYMMETRIES:
        errors.extend(_compliance_errors(material))

    hill_yield = getattr(material, "hill_yield", getattr(material, "hill48_yield", None))
    if hill_yield is not None:
        try:
            # Validated structurally so a Hill record defined elsewhere can
            # cross a package boundary without subclassing anything here.
            Hill48Yield(
                X=float(hill_yield.X),
                Y=float(hill_yield.Y),
                Z=float(hill_yield.Z),
                S12=float(hill_yield.S12),
                S13=float(hill_yield.S13),
                S23=float(hill_yield.S23),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            errors.append(f"hill_yield must provide valid X, Y, Z, S12, S13 and S23 strengths: {exc}")

    curve = getattr(material, "hardening_curve", None)
    if symmetry == "orthotropic" and curve is not None:
        if hill_yield is None:
            # Without directional strengths there is no orthotropic yield
            # surface for the curve to scale, so the analysis would silently
            # fall back to something isotropic.
            errors.append("orthotropic hardening_curve requires hill_yield directional strengths")
        if not callable(getattr(curve, "flow_stress", None)):
            errors.append("orthotropic hardening_curve must provide flow_stress(alpha)")
        if not callable(getattr(curve, "hardening_modulus", None)):
            errors.append("orthotropic hardening_curve must provide hardening_modulus(alpha)")

    return tuple(dict.fromkeys(errors))


def validate_material(material: Any) -> None:
    """Raise ``ValueError`` when a material violates the contract."""

    errors = material_validation_errors(material)
    if errors:
        label = getattr(material, "name", type(material).__name__)
        raise ValueError(f"Invalid structural material {label!r}: " + "; ".join(errors))
