"""Reductions from 3D compliance to what a formulation actually uses.

A shell needs a plane-stress matrix and a transverse-shear matrix; a beam needs
an axial modulus and two shear moduli.  Both are derived here from the 6x6
compliance rather than from re-entered engineering constants, so an isotropic
and an orthotropic material reach a formulation by the same path.

Rotation into an element frame is deliberately absent.  Material axes are a
material property; which physical direction axis 1 points along is a property of
the element, so the element rotates these matrices and this module never guesses
an orientation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

import numpy as np

from .contract import (
    SUPPORTED_ELASTIC_SYMMETRIES,
    elastic_compliance_matrix,
    material_symmetry,
)

__all__ = [
    "BeamMaterialProperties",
    "beam_material_properties",
    "shell_characteristic_modulus",
    "shell_material_matrices",
]


@dataclass(frozen=True)
class BeamMaterialProperties:
    """Elastic constants used by beam formulations in their local axes."""

    axial_modulus: float
    shear_modulus_xy: float
    shear_modulus_xz: float
    characteristic_modulus: float


def _require_supported_symmetry(material: Any, context: str) -> str:
    symmetry = material_symmetry(material)
    if symmetry not in SUPPORTED_ELASTIC_SYMMETRIES:
        raise NotImplementedError(
            f"Elastic symmetry {symmetry!r} is not supported; {context}"
        )
    return symmetry


def shell_material_matrices(material: Any) -> Tuple[np.ndarray, np.ndarray, float]:
    """Return material-axis shell ``(Q, G_transverse, G12)``.

    ``Q`` acts on ``[eps11, eps22, gamma12]`` and is obtained by inverting the
    corresponding *compliance* sub-block -- not by deleting rows from the 3D
    stiffness.  The distinction is the whole content of plane stress: the
    through-thickness strain is free, so eliminating ``sig33`` means inverting
    the reduced compliance, and a reduced stiffness would instead describe plane
    *strain* and overstiffen the shell by a factor involving the Poisson ratios.

    The transverse matrix acts on ``[gamma13, gamma23]``.  The third return
    value is the drilling shear modulus, used for the artificial in-plane
    rotational stiffness that shells with six DOF per node need.
    """

    _require_supported_symmetry(
        material,
        "general anisotropic materials require arbitrary constitutive coupling",
    )
    compliance = elastic_compliance_matrix(material)
    plane_indices = (0, 1, 5)
    # Voigt index 4 is 13 and index 3 is 23, so this ordering returns the
    # transverse shear matrix acting on [gamma13, gamma23] and not its
    # transpose.
    shear_indices = (4, 3)
    try:
        plane_stress = np.linalg.inv(compliance[np.ix_(plane_indices, plane_indices)])
        transverse_shear = np.linalg.inv(compliance[np.ix_(shear_indices, shear_indices)])
    except np.linalg.LinAlgError as exc:
        raise ValueError("Material compliance is singular for shell plane-stress reduction") from exc
    drilling_shear = 1.0 / float(compliance[5, 5])
    return plane_stress, transverse_shear, drilling_shear


def beam_material_properties(material: Any) -> BeamMaterialProperties:
    """Return local-axis beam elastic constants.

    Read from compliance diagonals, so an orthotropic material supplies a real
    ``E1``, ``G12`` and ``G13`` rather than being flattened into fabricated
    isotropic fields.
    """

    _require_supported_symmetry(
        material,
        "general anisotropic beam section stiffness is not implemented",
    )
    compliance = elastic_compliance_matrix(material)
    try:
        axial = 1.0 / float(compliance[0, 0])
        shear_xy = 1.0 / float(compliance[5, 5])
        shear_xz = 1.0 / float(compliance[4, 4])
    except (ZeroDivisionError, FloatingPointError) as exc:
        raise ValueError("Material compliance is singular for beam reduction") from exc
    return BeamMaterialProperties(
        axial_modulus=axial,
        shear_modulus_xy=shear_xy,
        shear_modulus_xz=shear_xz,
        characteristic_modulus=axial,
    )


def shell_characteristic_modulus(material: Any) -> float:
    """Return ``max(E1, E2)``, the shell numerical-scaling modulus.

    Used for penalty and drilling stiffness scaling and for convergence
    tolerances, where what is wanted is the magnitude of the stiffness rather
    than a physical constant.  Taking the larger in-plane modulus keeps those
    scales conservative for a strongly orthotropic material.
    """

    compliance = elastic_compliance_matrix(material)
    return max(1.0 / float(compliance[0, 0]), 1.0 / float(compliance[1, 1]))
