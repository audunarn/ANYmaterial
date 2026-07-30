"""Directional yield criteria.

Hill-48 in its symmetric form: six uniaxial and shear strengths in the material
axes, from which the conventional ``F`` through ``N`` coefficients follow.  The
quadratic is written as a *utilization squared* -- dimensionless, unity at
yield -- rather than as a stress, so that comparing two directions never
depends on which strength was chosen as the reference.

Both a class and free functions are provided.  The free functions consume the
six-strength protocol by attribute lookup, so a consumer can evaluate Hill
utilization for any object exposing ``X``, ``Y``, ``Z``, ``S12``, ``S13`` and
``S23`` without importing :class:`Hill48Yield`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

__all__ = [
    "Hill48Yield",
    "hill48_coefficients",
    "hill48_equivalent_stress",
    "hill48_strengths",
]

_STRENGTH_NAMES: Tuple[str, ...] = ("X", "Y", "Z", "S12", "S13", "S23")


def _normal_block(F: float, G: float, H: float) -> np.ndarray:
    """The 3x3 normal-stress block of the Hill quadratic."""

    return np.asarray(
        [
            [G + H, -H, -G],
            [-H, F + H, -F],
            [-G, -F, F + G],
        ],
        dtype=float,
    )


def _assert_convex_normal_block(F: float, G: float, H: float) -> None:
    """Raise unless the normal-stress quadratic is convex and bounded.

    The block has one intentional null direction -- hydrostatic stress, which
    Hill-48 does not resist -- so the test is that the remaining eigenvalues
    are nonnegative.  Checking the complete quadratic this way is both less
    restrictive and more accurate than requiring each of ``F``, ``G`` and ``H``
    to be positive individually: strength ratios that are perfectly admissible
    can make one coefficient negative without making the surface non-convex.
    """

    eigenvalues = np.linalg.eigvalsh(_normal_block(F, G, H))
    scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
    if float(np.min(eigenvalues)) < -1.0e-12 * scale:
        raise ValueError("Hill-48 strengths do not define a convex quadratic yield surface")


def hill48_strengths(yield_model: Any) -> Tuple[float, float, float, float, float, float]:
    """Return and validate the six symmetric Hill-48 strengths.

    ``yield_model`` is consumed by protocol rather than by a concrete import,
    so any object exposing the six named strengths works.
    """

    values = []
    for name in _STRENGTH_NAMES:
        try:
            value = float(getattr(yield_model, name))
        except (AttributeError, TypeError, ValueError) as exc:
            raise TypeError(
                "yield_model must provide finite positive X, Y, Z, S12, S13 and S23 strengths"
            ) from exc
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"Hill-48 strength {name} must be finite and positive")
        values.append(value)

    X, Y, Z, S12, S13, S23 = values
    ratios = np.asarray([X / Y, X / Z, X / S12, X / S13, X / S23], dtype=float)
    if np.any(~np.isfinite(ratios)) or np.any(ratios <= 0.0):
        raise ValueError("Hill-48 strength ratios must be finite and positive")

    # Convexity on the dimensionless normal block, which is scale-free and so
    # behaves identically for strengths in Pa and in MPa.
    xy2 = (X / Y) ** 2
    xz2 = (X / Z) ** 2
    _assert_convex_normal_block(
        F=0.5 * (xy2 + xz2 - 1.0),
        G=0.5 * (xz2 + 1.0 - xy2),
        H=0.5 * (1.0 + xy2 - xz2),
    )
    return X, Y, Z, S12, S13, S23


def hill48_coefficients(yield_model: Any) -> Dict[str, float]:
    """Return the standard 3-D Hill-48 coefficients ``F`` through ``N``.

    The convention is

    ``F(s2-s3)^2 + G(s3-s1)^2 + H(s1-s2)^2
       + 2L*t23^2 + 2M*t13^2 + 2N*t12^2 = 1``.
    """

    X, Y, Z, S12, S13, S23 = hill48_strengths(yield_model)
    inv_x2 = 1.0 / X**2
    inv_y2 = 1.0 / Y**2
    inv_z2 = 1.0 / Z**2
    coefficients = {
        "F": 0.5 * (inv_y2 + inv_z2 - inv_x2),
        "G": 0.5 * (inv_z2 + inv_x2 - inv_y2),
        "H": 0.5 * (inv_x2 + inv_y2 - inv_z2),
        "L": 0.5 / S23**2,
        "M": 0.5 / S13**2,
        "N": 0.5 / S12**2,
    }
    if any(not np.isfinite(value) for value in coefficients.values()):
        raise ValueError("Hill-48 coefficients must be finite")
    return coefficients


def hill48_equivalent_stress(stress: Any, yield_model: Any) -> np.ndarray:
    """Return ``X``-referenced 3-D Hill equivalent stress.

    Stress order is engineering Voigt ``[11, 22, 33, 23, 13, 12]``.  Accepts any
    trailing-``(6,)`` array, so a whole field of integration points can be
    evaluated in one call.
    """

    values = np.asarray(stress, dtype=float)
    if values.ndim == 0 or values.shape[-1:] != (6,):
        raise ValueError("stress must have shape (..., 6)")
    if np.any(~np.isfinite(values)):
        raise ValueError("stress must contain only finite values")
    coefficients = hill48_coefficients(yield_model)
    s1, s2, s3, t23, t13, t12 = np.moveaxis(values, -1, 0)
    utilization_squared = (
        coefficients["F"] * (s2 - s3) ** 2
        + coefficients["G"] * (s3 - s1) ** 2
        + coefficients["H"] * (s1 - s2) ** 2
        + 2.0 * coefficients["L"] * t23**2
        + 2.0 * coefficients["M"] * t13**2
        + 2.0 * coefficients["N"] * t12**2
    )
    # A negative value here can only come from round-off on a convex form, so
    # it is clamped -- but a *large* negative value means the coefficients are
    # not convex after all, and that must not be silently squared away.
    scale = np.maximum(np.sum(values * values, axis=-1), 1.0)
    if np.any(utilization_squared < -1.0e-12 * scale):
        raise FloatingPointError("Hill equivalent stress squared is negative")
    return float(yield_model.X) * np.sqrt(np.maximum(utilization_squared, 0.0))


@dataclass(frozen=True)
class Hill48Yield:
    """Symmetric Hill-48 directional yield strengths in material axes.

    ``X``, ``Y`` and ``Z`` are uniaxial strengths in directions 1, 2 and 3.
    ``S12``, ``S13`` and ``S23`` are the corresponding shear strengths.  All
    values are physical stresses in Pa.
    """

    X: float
    Y: float
    Z: float
    S12: float
    S13: float
    S23: float

    def __post_init__(self) -> None:
        values = np.asarray((self.X, self.Y, self.Z, self.S12, self.S13, self.S23), dtype=float)
        if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
            raise ValueError("Hill-48 strengths X, Y, Z, S12, S13 and S23 must be finite and positive")

        eigvals = np.linalg.eigvalsh(self.quadratic_form_matrix())
        scale = max(float(np.max(np.abs(eigvals))), np.finfo(float).tiny)
        tolerance = 1.0e-12 * scale
        # Hydrostatic stress supplies the one expected null direction.  Every
        # deviatoric normal and shear direction must remain bounded.
        if float(eigvals[0]) < -tolerance or float(eigvals[1]) <= tolerance:
            raise ValueError(
                "Hill-48 strengths do not define a convex, bounded deviatoric yield surface"
            )

    def coefficients(self) -> Tuple[float, float, float, float, float, float]:
        """Return conventional ``(F, G, H, L, M, N)`` coefficients.

        The resulting quadratic form is a dimensionless utilization squared:

        ``F(s2-s3)^2 + G(s3-s1)^2 + H(s1-s2)^2
        + 2L*t23^2 + 2M*t13^2 + 2N*t12^2``.
        """

        x2 = float(self.X) ** 2
        y2 = float(self.Y) ** 2
        z2 = float(self.Z) ** 2
        s12_2 = float(self.S12) ** 2
        s13_2 = float(self.S13) ** 2
        s23_2 = float(self.S23) ** 2
        F = 0.5 * (1.0 / y2 + 1.0 / z2 - 1.0 / x2)
        G = 0.5 * (1.0 / z2 + 1.0 / x2 - 1.0 / y2)
        H = 0.5 * (1.0 / x2 + 1.0 / y2 - 1.0 / z2)
        L = 0.5 / s23_2
        M = 0.5 / s13_2
        N = 0.5 / s12_2
        return F, G, H, L, M, N

    @property
    def F(self) -> float:
        return self.coefficients()[0]

    @property
    def G(self) -> float:
        return self.coefficients()[1]

    @property
    def H(self) -> float:
        return self.coefficients()[2]

    @property
    def L(self) -> float:
        return self.coefficients()[3]

    @property
    def M(self) -> float:
        return self.coefficients()[4]

    @property
    def N(self) -> float:
        return self.coefficients()[5]

    def quadratic_form_matrix(self) -> np.ndarray:
        """Return the 6x6 utilization-squared matrix in Voigt order."""

        F, G, H, L, M, N = self.coefficients()
        matrix = np.zeros((6, 6), dtype=float)
        matrix[:3, :3] = _normal_block(F, G, H)
        matrix[3, 3] = 2.0 * L
        matrix[4, 4] = 2.0 * M
        matrix[5, 5] = 2.0 * N
        return matrix

    def plane_stress_quadratic_matrix(self) -> np.ndarray:
        """Return the material-axis plane-stress matrix for ``[s11,s22,t12]``."""

        indices = (0, 1, 5)
        matrix = self.quadratic_form_matrix()
        return matrix[np.ix_(indices, indices)]

    def utilization(self, stress: Any) -> np.ndarray | float:
        """Evaluate Hill utilization for one or more 6-component stresses."""

        values = np.asarray(stress, dtype=float)
        if values.shape == (6,):
            phi = float(values @ self.quadratic_form_matrix() @ values)
            return float(np.sqrt(max(phi, 0.0)))
        if values.ndim < 1 or values.shape[-1] != 6:
            raise ValueError("Hill-48 stress must have trailing shape (6,)")
        phi = np.einsum("...i,ij,...j->...", values, self.quadratic_form_matrix(), values)
        return np.sqrt(np.maximum(phi, 0.0))

    def equivalent_stress(self, stress: Any, reference_stress: Optional[float] = None) -> np.ndarray | float:
        """Return a stress-valued Hill equivalent referenced to ``X`` by default."""

        reference = float(self.X if reference_stress is None else reference_stress)
        if not np.isfinite(reference) or reference <= 0.0:
            raise ValueError("Hill-48 reference stress must be finite and positive")
        return reference * self.utilization(stress)

    def as_dict(self) -> Dict[str, float]:
        """Return a JSON-safe mapping of the six strengths."""

        return {name: float(getattr(self, name)) for name in _STRENGTH_NAMES}

    @classmethod
    def from_dict(cls, data: Any) -> "Hill48Yield":
        """Build from a mapping of the six strengths."""

        try:
            return cls(**{name: float(data[name]) for name in _STRENGTH_NAMES})
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Hill-48 strengths require all of {', '.join(_STRENGTH_NAMES)}"
            ) from exc
