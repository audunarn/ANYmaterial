"""Isotropic engineering materials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .validation import validate_material

__all__ = ["IsotropicMaterial"]


@dataclass
class IsotropicMaterial:
    """A homogeneous isotropic material in SI units.

    ``hardening_curve`` is what makes the material nonlinear.  Left as ``None``
    the material stays linear elastic, and a nonlinear analysis of it is
    geometrically nonlinear only -- a different analysis, and one worth asking
    for explicitly rather than arriving at by omission.

    ``yield_stress`` is carried even when there is no curve, because a linear
    analysis still reports utilization against it.
    """

    name: str
    elastic_modulus: float
    poisson_ratio: float
    density: float = 0.0
    yield_stress: float = 0.0
    hardening_curve: Optional[object] = None

    def __post_init__(self) -> None:
        validate_material(self)

    @property
    def elastic_symmetry(self) -> str:
        return "isotropic"

    @property
    def shear_modulus(self) -> float:
        """``G = E / 2(1 + nu)``, exact for isotropy rather than independent."""

        return self.elastic_modulus / (2.0 * (1.0 + self.poisson_ratio))

    @property
    def bulk_modulus(self) -> float:
        """``K = E / 3(1 - 2nu)``."""

        return self.elastic_modulus / (3.0 * (1.0 - 2.0 * self.poisson_ratio))

    @property
    def is_nonlinear(self) -> bool:
        """Whether this material yields, rather than staying elastic."""

        return self.hardening_curve is not None

    def elastic_compliance_matrix(self) -> np.ndarray:
        """Return 3D engineering compliance in ``[11,22,33,23,13,12]`` order."""

        E = float(self.elastic_modulus)
        nu = float(self.poisson_ratio)
        G = float(self.shear_modulus)
        return np.array(
            [
                [1.0 / E, -nu / E, -nu / E, 0.0, 0.0, 0.0],
                [-nu / E, 1.0 / E, -nu / E, 0.0, 0.0, 0.0],
                [-nu / E, -nu / E, 1.0 / E, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0 / G, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0 / G, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0 / G],
            ],
            dtype=float,
        )
