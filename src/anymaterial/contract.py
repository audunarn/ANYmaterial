"""The structural material contract.

A consumer needs four things from a material: a name, a density, a declared
elastic symmetry, and a 6x6 engineering compliance.  Everything else -- shell
plane-stress matrices, beam axial and shear constants, yield surfaces -- is
derived from those, in :mod:`anymaterial.reductions` and elsewhere.

The contract is a :class:`typing.Protocol` rather than a base class on purpose.
A solver should accept a material without importing the class that defines it,
which is what allows this package and its consumers to be released
independently.  Validation is therefore written against attributes, not types.

Voigt order is engineering ``[11, 22, 33, 23, 13, 12]``:

``[eps11, eps22, eps33, gamma23, gamma13, gamma12] = S @
  [sig11, sig22, sig33, tau23, tau13, tau12]``

Shear strains are engineering angles, twice the tensor components.  Getting
this wrong scales every shear term by two and is not detectable from the
diagonal, so the order is stated once here and matched everywhere.
"""

from __future__ import annotations

from typing import Any, Protocol, Tuple, runtime_checkable

import numpy as np

__all__ = [
    "ENGINEERING_VOIGT_ORDER",
    "SUPPORTED_ELASTIC_SYMMETRIES",
    "StructuralMaterial",
    "elastic_compliance_matrix",
    "is_isotropic_material",
    "is_orthotropic_material",
    "material_symmetry",
]


ENGINEERING_VOIGT_ORDER: Tuple[str, ...] = ("11", "22", "33", "23", "13", "12")

SUPPORTED_ELASTIC_SYMMETRIES = frozenset({"isotropic", "orthotropic"})


@runtime_checkable
class StructuralMaterial(Protocol):
    """Minimal contract for a structural material."""

    name: str
    density: float
    elastic_symmetry: str

    def elastic_compliance_matrix(self) -> np.ndarray:
        """Return the 6x6 engineering compliance in Voigt order."""


def material_symmetry(material: Any) -> str:
    """Return the normalized declared elastic symmetry.

    Duck-typed isotropic objects that predate the declaration stay recognizable
    when they expose the historical ``elastic_modulus`` and ``poisson_ratio``
    fields.  That fallback exists for material records arriving from older
    callers and deserializers, not as an alternative to declaring the symmetry.
    """

    symmetry = getattr(material, "elastic_symmetry", None)
    if symmetry is None and hasattr(material, "elastic_modulus") and hasattr(material, "poisson_ratio"):
        return "isotropic"
    if not isinstance(symmetry, str) or not symmetry.strip():
        raise ValueError(
            "Structural material must declare elastic_symmetry as 'isotropic' or 'orthotropic'"
        )
    return symmetry.strip().lower()


def is_isotropic_material(material: Any) -> bool:
    """Return whether a material declares isotropic elasticity."""

    try:
        return material_symmetry(material) == "isotropic"
    except ValueError:
        return False


def is_orthotropic_material(material: Any) -> bool:
    """Return whether a material declares orthotropic elasticity."""

    try:
        return material_symmetry(material) == "orthotropic"
    except ValueError:
        return False


def elastic_compliance_matrix(material: Any) -> np.ndarray:
    """Return a material's compliance with a stable numpy representation.

    A material that provides ``elastic_compliance_matrix()`` is asked for it.
    A legacy isotropic record that does not is assembled from ``E`` and ``nu``,
    so the two reach every reduction by the same path and there is one place
    for the algebra to be wrong.
    """

    provider = getattr(material, "elastic_compliance_matrix", None)
    if callable(provider):
        matrix = np.asarray(provider(), dtype=float)
    elif is_isotropic_material(material):
        E = float(material.elastic_modulus)
        nu = float(material.poisson_ratio)
        G = E / (2.0 * (1.0 + nu))
        matrix = np.array(
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
    else:
        raise ValueError("Structural material must provide elastic_compliance_matrix()")
    if matrix.shape != (6, 6):
        raise ValueError(
            f"Material elastic compliance must have shape (6, 6), received {matrix.shape}"
        )
    return matrix
