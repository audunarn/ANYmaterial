"""Orthotropic engineering materials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .validation import validate_material
from .yield_criteria import Hill48Yield

__all__ = ["OrthotropicMaterial"]


@dataclass
class OrthotropicMaterial:
    """Homogeneous three-dimensional orthotropic engineering material.

    Nine independent constants: three moduli, three shear moduli and three
    Poisson ratios.  The remaining three Poisson ratios are *not* independent --
    reciprocity fixes them -- so they are exposed as properties rather than
    fields.  Accepting all six as input is the classic way to end up with a
    non-symmetric compliance that no longer describes a real material.

    Direction 1 is the primary material axis.  Which physical direction that is
    depends on the element, so orientation belongs to the element and not here.
    """

    name: str
    elastic_modulus_1: float
    elastic_modulus_2: float
    elastic_modulus_3: float
    poisson_ratio_12: float
    poisson_ratio_13: float
    poisson_ratio_23: float
    shear_modulus_12: float
    shear_modulus_13: float
    shear_modulus_23: float
    density: float = 0.0
    hill_yield: Optional[Hill48Yield] = None
    hardening_curve: Optional[object] = None

    def __post_init__(self) -> None:
        validate_material(self)

    @property
    def elastic_symmetry(self) -> str:
        return "orthotropic"

    @property
    def poisson_ratio_21(self) -> float:
        return float(self.poisson_ratio_12) * float(self.elastic_modulus_2) / float(self.elastic_modulus_1)

    @property
    def poisson_ratio_31(self) -> float:
        return float(self.poisson_ratio_13) * float(self.elastic_modulus_3) / float(self.elastic_modulus_1)

    @property
    def poisson_ratio_32(self) -> float:
        return float(self.poisson_ratio_23) * float(self.elastic_modulus_3) / float(self.elastic_modulus_2)

    @property
    def hill48_yield(self) -> Optional[Hill48Yield]:
        """Compatibility spelling for consumers that name the criterion."""

        return self.hill_yield

    @property
    def is_nonlinear(self) -> bool:
        """Whether this material yields, rather than staying elastic."""

        return self.hardening_curve is not None

    def elastic_compliance_matrix(self) -> np.ndarray:
        """Return symmetric 3D engineering compliance in material axes."""

        E1 = float(self.elastic_modulus_1)
        E2 = float(self.elastic_modulus_2)
        E3 = float(self.elastic_modulus_3)
        nu12 = float(self.poisson_ratio_12)
        nu13 = float(self.poisson_ratio_13)
        nu23 = float(self.poisson_ratio_23)
        matrix = np.zeros((6, 6), dtype=float)
        matrix[0, 0] = 1.0 / E1
        matrix[1, 1] = 1.0 / E2
        matrix[2, 2] = 1.0 / E3
        matrix[0, 1] = matrix[1, 0] = -nu12 / E1
        matrix[0, 2] = matrix[2, 0] = -nu13 / E1
        matrix[1, 2] = matrix[2, 1] = -nu23 / E2
        matrix[3, 3] = 1.0 / float(self.shear_modulus_23)
        matrix[4, 4] = 1.0 / float(self.shear_modulus_13)
        matrix[5, 5] = 1.0 / float(self.shear_modulus_12)
        return matrix
