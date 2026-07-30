"""A serializable material specification.

A live material carries a hardening-curve *object*, which cannot be written to a
project file.  A specification instead records **how to rebuild** the curve --
``{"kind": "dnv_c208", "grade": "S355", "thickness": 0.02}`` -- so a saved
material comes back identical rather than coming back elastic.  A material that
silently loses its hardening on save turns a plastic analysis into an elastic one
without saying so, which is the failure this module exists to prevent.

For the same reason the conversion in the other direction fails closed: a curve
this module cannot describe raises rather than serializing as ``None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .curves import (
    DNVC208MaterialCurve,
    LinearHardeningCurve,
    PiecewiseLinearCurve,
    PowerLawHardeningCurve,
    curve_from_properties,
)
from .isotropic import IsotropicMaterial
from .orthotropic import OrthotropicMaterial
from .yield_criteria import Hill48Yield

__all__ = [
    "MaterialSpec",
    "build_hardening_curve",
    "hardening_descriptor",
    "load_specs",
    "save_specs",
    "spec_from_material",
]

_ISOTROPIC_CONSTANTS = ("elastic_modulus", "poisson_ratio")

_ORTHOTROPIC_CONSTANTS = (
    "elastic_modulus_1",
    "elastic_modulus_2",
    "elastic_modulus_3",
    "poisson_ratio_12",
    "poisson_ratio_13",
    "poisson_ratio_23",
    "shear_modulus_12",
    "shear_modulus_13",
    "shear_modulus_23",
)

_REQUIRED_CONSTANTS = {
    "isotropic": _ISOTROPIC_CONSTANTS,
    "orthotropic": _ORTHOTROPIC_CONSTANTS,
}


def build_hardening_curve(descriptor: Optional[Mapping[str, Any]]) -> Optional[Any]:
    """Rebuild a hardening curve from its descriptor, or return ``None``."""

    if descriptor is None:
        return None
    data = dict(descriptor)
    kind = str(data.pop("kind", "")).strip().lower()
    try:
        if kind == "dnv_c208":
            # Resolved through the table every time rather than from a stored
            # copy, so a saved material always uses the current tabulated curve.
            from .library import dnv_c208_steel_curve

            return dnv_c208_steel_curve(str(data["grade"]), float(data["thickness"]))
        if kind == "dnv_c208_explicit":
            return curve_from_properties(data)
        if kind == "linear":
            return LinearHardeningCurve(
                sigma_yield=float(data["sigma_yield"]),
                hardening_modulus_value=float(data.get("hardening_modulus", 0.0)),
            )
        if kind == "piecewise_linear":
            return PiecewiseLinearCurve.from_points(
                [(float(strain), float(stress)) for strain, stress in data["points"]]
            )
        if kind == "power_law":
            if "eps_0" in data:
                return PowerLawHardeningCurve(
                    K=float(data["K"]), n=float(data["n"]), eps_0=float(data["eps_0"])
                )
            return PowerLawHardeningCurve.from_yield(
                sigma_yield=float(data["sigma_yield"]), K=float(data["K"]), n=float(data["n"])
            )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"incomplete {kind!r} hardening descriptor: {exc}") from exc
    raise ValueError(
        f"unknown hardening kind {kind!r}; use one of 'dnv_c208', 'dnv_c208_explicit', "
        "'linear', 'piecewise_linear', 'power_law'"
    )


def hardening_descriptor(curve: Any) -> Dict[str, Any]:
    """Describe a hardening curve so it can be rebuilt.

    Raises for a curve this module does not recognize.  Returning ``None``
    instead would produce a specification that saves and reloads as an elastic
    material, which is the one outcome worth refusing.
    """

    if isinstance(curve, DNVC208MaterialCurve):
        # The grade and thickness a table lookup started from are not recoverable
        # from the curve, so the seven parameters are stored explicitly.  The
        # curve is identical; only its provenance is lost.
        return {"kind": "dnv_c208_explicit", **curve.as_dict()}
    if isinstance(curve, LinearHardeningCurve):
        return {
            "kind": "linear",
            "sigma_yield": float(curve.sigma_yield),
            "hardening_modulus": float(curve.hardening_modulus_value),
        }
    if isinstance(curve, PiecewiseLinearCurve):
        return {
            "kind": "piecewise_linear",
            "points": [
                [float(strain), float(stress)]
                for strain, stress in zip(curve.plastic_strain, curve.flow_stress_values)
            ],
        }
    if isinstance(curve, PowerLawHardeningCurve):
        return {
            "kind": "power_law",
            "K": float(curve.K),
            "n": float(curve.n),
            "eps_0": float(curve.eps_0),
        }
    raise ValueError(
        f"cannot serialize hardening curve of type {type(curve).__name__}; "
        "a specification that dropped it would reload as an elastic material"
    )


@dataclass
class MaterialSpec:
    """A material described by data only, ready to be written to a file."""

    name: str
    symmetry: str = "isotropic"
    constants: Dict[str, float] = field(default_factory=dict)
    density: float = 0.0
    yield_stress: float = 0.0
    hardening: Optional[Dict[str, Any]] = None
    hill: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("material name must be a non-empty string")
        self.symmetry = str(self.symmetry).strip().lower()
        if self.symmetry not in _REQUIRED_CONSTANTS:
            raise ValueError(
                f"elastic symmetry {self.symmetry!r} is not supported; use 'isotropic' or 'orthotropic'"
            )
        self.constants = {str(key): float(value) for key, value in dict(self.constants).items()}
        missing = [name for name in _REQUIRED_CONSTANTS[self.symmetry] if name not in self.constants]
        if missing:
            raise ValueError(f"{self.symmetry} material {self.name!r} is missing constants: {missing}")
        if self.hill is not None:
            # Validated on construction so a malformed strength set is caught
            # when the file is read, not when a plastic solve first needs it.
            Hill48Yield.from_dict(self.hill)

    @property
    def is_nonlinear(self) -> bool:
        """Whether this specification yields, rather than staying elastic."""

        return self.hardening is not None

    def hardening_curve(self) -> Optional[Any]:
        """Build the hardening curve this specification describes, or ``None``."""

        return build_hardening_curve(self.hardening)

    def build(self) -> IsotropicMaterial | OrthotropicMaterial:
        """Construct and validate the live material."""

        curve = self.hardening_curve()
        if self.symmetry == "isotropic":
            return IsotropicMaterial(
                name=self.name,
                elastic_modulus=self.constants["elastic_modulus"],
                poisson_ratio=self.constants["poisson_ratio"],
                density=self.density,
                yield_stress=self.yield_stress,
                hardening_curve=curve,
            )
        return OrthotropicMaterial(
            name=self.name,
            elastic_modulus_1=self.constants["elastic_modulus_1"],
            elastic_modulus_2=self.constants["elastic_modulus_2"],
            elastic_modulus_3=self.constants["elastic_modulus_3"],
            poisson_ratio_12=self.constants["poisson_ratio_12"],
            poisson_ratio_13=self.constants["poisson_ratio_13"],
            poisson_ratio_23=self.constants["poisson_ratio_23"],
            shear_modulus_12=self.constants["shear_modulus_12"],
            shear_modulus_13=self.constants["shear_modulus_13"],
            shear_modulus_23=self.constants["shear_modulus_23"],
            density=self.density,
            hill_yield=Hill48Yield.from_dict(self.hill) if self.hill else None,
            hardening_curve=curve,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe mapping."""

        data: Dict[str, Any] = {
            "name": self.name,
            "symmetry": self.symmetry,
            "constants": dict(self.constants),
            "density": float(self.density),
            "yield_stress": float(self.yield_stress),
        }
        if self.hardening is not None:
            data["hardening"] = dict(self.hardening)
        if self.hill is not None:
            data["hill"] = dict(self.hill)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialSpec":
        """Build from a mapping produced by :meth:`to_dict`."""

        try:
            return cls(
                name=str(data["name"]),
                symmetry=str(data.get("symmetry", "isotropic")),
                constants=dict(data.get("constants", {})),
                density=float(data.get("density", 0.0)),
                yield_stress=float(data.get("yield_stress", 0.0)),
                hardening=dict(data["hardening"]) if data.get("hardening") else None,
                hill=dict(data["hill"]) if data.get("hill") else None,
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"malformed material specification: {exc}") from exc

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "MaterialSpec":
        return cls.from_dict(json.loads(text))


def spec_from_material(material: Any) -> MaterialSpec:
    """Describe a live material as a specification.

    Raises when the material carries a hardening curve that cannot be described,
    rather than producing a specification that would reload as elastic.
    """

    from .contract import material_symmetry

    symmetry = material_symmetry(material)
    if symmetry not in _REQUIRED_CONSTANTS:
        raise ValueError(
            f"elastic symmetry {symmetry!r} is not supported; use 'isotropic' or 'orthotropic'"
        )
    constants = {}
    for name in _REQUIRED_CONSTANTS[symmetry]:
        if not hasattr(material, name):
            raise ValueError(
                f"material {getattr(material, 'name', '<unnamed>')!r} does not expose {name}, "
                "so it cannot be described as a specification"
            )
        constants[name] = float(getattr(material, name))

    curve = getattr(material, "hardening_curve", None)
    hill = getattr(material, "hill_yield", getattr(material, "hill48_yield", None))
    return MaterialSpec(
        name=str(material.name),
        symmetry=symmetry,
        constants=constants,
        density=float(getattr(material, "density", 0.0)),
        yield_stress=float(getattr(material, "yield_stress", 0.0)),
        hardening=hardening_descriptor(curve) if curve is not None else None,
        hill=Hill48Yield.from_dict(
            {name: getattr(hill, name) for name in ("X", "Y", "Z", "S12", "S13", "S23")}
        ).as_dict()
        if hill is not None
        else None,
    )


def save_specs(path: str | Path, specs: Sequence[MaterialSpec], *, overwrite: bool = False) -> Path:
    """Write a list of specifications to a JSON file."""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {destination}")
    payload = {"materials": [spec.to_dict() for spec in specs]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_specs(path: str | Path) -> List[MaterialSpec]:
    """Read a list of specifications from a JSON file.

    Accepts a single specification object as well as a ``{"materials": [...]}``
    document, because a one-material file is the common case when a material is
    exported to be shared.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, Mapping) and "materials" in data:
        entries = data["materials"]
    elif isinstance(data, Mapping):
        entries = [data]
    elif isinstance(data, list):
        entries = data
    else:
        raise ValueError("material file must contain an object or a list of objects")
    return [MaterialSpec.from_dict(entry) for entry in entries]
