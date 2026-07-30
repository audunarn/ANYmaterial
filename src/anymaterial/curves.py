"""Nonlinear hardening curves.

A hardening curve answers one question: given an equivalent plastic strain, what
is the flow stress, and how fast is it changing.  Both are needed -- the stress
for the yield condition and the slope for the consistent tangent -- and both are
evaluated for every integration point and thickness layer at once, so every
implementation here is vectorized over numpy arrays.  Vectorization is part of
the contract, not an optimization.

Curves are expressed in **true stress and true plastic strain**.  The
distinction matters past a few percent strain: engineering values diverge from
true values exactly where a plastic analysis is interesting.

Four curves are provided:

* :class:`LinearHardeningCurve` -- bilinear, the standard engineering
  idealization.
* :class:`PiecewiseLinearCurve` -- a tabulated curve, for measured data.
* :class:`PowerLawHardeningCurve` -- Swift/Hollomon ``K(eps_0 + eps_p)^n``.
* :class:`DNVC208MaterialCurve` -- the DNV-RP-C208 section 4.6.6 form.

Ramberg-Osgood is deliberately absent.  It has no distinct yield point: as a
flow curve its stress tends to zero as plastic strain does, which a return
mapping cannot use, and the usual repairs turn it into a different curve while
keeping the name.  :class:`PowerLawHardeningCurve` covers the same behaviour
with an explicit yield stress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol, Sequence, Tuple, runtime_checkable

import numpy as np

__all__ = [
    "DNVC208MaterialCurve",
    "HardeningCurve",
    "LinearHardeningCurve",
    "PiecewiseLinearCurve",
    "PowerLawHardeningCurve",
    "curve_from_properties",
]


@runtime_checkable
class HardeningCurve(Protocol):
    """The contract a consumer needs from a hardening curve."""

    def flow_stress(self, eps_p: np.ndarray) -> np.ndarray:
        """Flow (yield) stress at an equivalent plastic strain, in Pa."""

    def hardening_modulus(self, eps_p: np.ndarray) -> np.ndarray:
        """``d(flow stress)/d(equivalent plastic strain)``, in Pa."""


def _plastic_strain(eps_p: Any) -> np.ndarray:
    """Coerce to a non-negative float array.

    Negative equivalent plastic strain is not a physical state; it appears only
    as round-off in a return mapping, and clamping is the right response.
    """

    return np.maximum(np.asarray(eps_p, dtype=float), 0.0)


@dataclass(frozen=True)
class LinearHardeningCurve:
    """Bilinear hardening: ``sigma = sigma_yield + H * eps_p``.

    ``hardening_modulus`` is the *plastic* modulus, the slope in stress against
    plastic strain -- not the elastic-plastic tangent in total strain.  For a
    tangent modulus ``Et`` measured against total strain the conversion is
    ``H = Et * E / (E - Et)``.  Confusing the two is the most common way a
    bilinear model comes out far too stiff.

    ``H = 0`` is perfect plasticity and is allowed.
    """

    sigma_yield: float
    hardening_modulus_value: float = 0.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.sigma_yield) or self.sigma_yield <= 0.0:
            raise ValueError("sigma_yield must be finite and positive")
        if not np.isfinite(self.hardening_modulus_value):
            raise ValueError("hardening modulus must be finite")
        if self.hardening_modulus_value < 0.0:
            raise ValueError(
                "hardening modulus must not be negative; softening is not supported "
                "by this curve because it makes the tangent indefinite"
            )

    def flow_stress(self, eps_p: np.ndarray) -> np.ndarray:
        strain = _plastic_strain(eps_p)
        return float(self.sigma_yield) + float(self.hardening_modulus_value) * strain

    def hardening_modulus(self, eps_p: np.ndarray) -> np.ndarray:
        strain = _plastic_strain(eps_p)
        return np.full_like(strain, float(self.hardening_modulus_value))


@dataclass(frozen=True)
class PiecewiseLinearCurve:
    """A tabulated flow curve, linear between points and flat beyond the last.

    ``plastic_strain`` must start at zero, because the first flow stress *is*
    the initial yield stress and a table starting elsewhere leaves the onset of
    yielding undefined.

    Past the last tabulated point the curve is perfectly plastic rather than
    extrapolated along the final slope.  Extrapolating a measured curve invents
    strength that was never measured, and it does so precisely in the range
    where an analysis is being pushed hard enough to care.
    """

    plastic_strain: Tuple[float, ...]
    flow_stress_values: Tuple[float, ...]

    def __post_init__(self) -> None:
        strains = np.asarray(self.plastic_strain, dtype=float)
        stresses = np.asarray(self.flow_stress_values, dtype=float)
        if strains.ndim != 1 or stresses.ndim != 1:
            raise ValueError("plastic_strain and flow_stress_values must be one-dimensional")
        if strains.size != stresses.size:
            raise ValueError("plastic_strain and flow_stress_values must have equal length")
        if strains.size < 2:
            raise ValueError("a piecewise linear curve needs at least two points")
        if not np.all(np.isfinite(strains)) or not np.all(np.isfinite(stresses)):
            raise ValueError("curve points must be finite")
        if float(strains[0]) != 0.0:
            raise ValueError("plastic_strain must start at 0.0, where the flow stress is the initial yield")
        if not np.all(np.diff(strains) > 0.0):
            raise ValueError("plastic_strain must be strictly increasing")
        if np.any(stresses <= 0.0):
            raise ValueError("flow stresses must be positive")
        if np.any(np.diff(stresses) < 0.0):
            raise ValueError(
                "flow stresses must not decrease; softening is not supported by this curve "
                "because it makes the tangent indefinite"
            )

    def _strains(self) -> np.ndarray:
        return np.asarray(self.plastic_strain, dtype=float)

    def _stresses(self) -> np.ndarray:
        return np.asarray(self.flow_stress_values, dtype=float)

    @classmethod
    def from_points(cls, points: Sequence[Tuple[float, float]]) -> "PiecewiseLinearCurve":
        """Build from ``[(eps_p, sigma), ...]`` pairs."""

        ordered = [(float(strain), float(stress)) for strain, stress in points]
        return cls(
            plastic_strain=tuple(strain for strain, _stress in ordered),
            flow_stress_values=tuple(stress for _strain, stress in ordered),
        )

    def flow_stress(self, eps_p: np.ndarray) -> np.ndarray:
        # np.interp clamps outside the table, which is exactly the flat
        # extrapolation this curve promises.
        return np.interp(_plastic_strain(eps_p), self._strains(), self._stresses())

    def hardening_modulus(self, eps_p: np.ndarray) -> np.ndarray:
        strain = _plastic_strain(eps_p)
        strains = self._strains()
        slopes = np.diff(self._stresses()) / np.diff(strains)
        index = np.clip(np.searchsorted(strains, strain, side="right") - 1, 0, slopes.size - 1)
        return np.where(strain >= strains[-1], 0.0, slopes[index])


@dataclass(frozen=True)
class PowerLawHardeningCurve:
    """Swift/Hollomon power law: ``sigma = K * (eps_0 + eps_p) ** n``.

    ``eps_0`` shifts the curve so the flow stress at zero plastic strain is
    finite and equal to the initial yield.  Without it a pure ``K * eps_p ** n``
    starts at zero stress, which no return mapping can use.  Build from a yield
    stress with :meth:`from_yield` rather than solving for ``eps_0`` by hand.
    """

    K: float
    n: float
    eps_0: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.K) or self.K <= 0.0:
            raise ValueError("K must be finite and positive")
        if not np.isfinite(self.n) or not (0.0 < self.n < 1.0):
            raise ValueError("require 0 < n < 1")
        if not np.isfinite(self.eps_0) or self.eps_0 <= 0.0:
            raise ValueError("eps_0 must be finite and positive, or the curve starts at zero stress")

    @classmethod
    def from_yield(cls, sigma_yield: float, K: float, n: float) -> "PowerLawHardeningCurve":
        """Build the curve passing exactly through ``sigma_yield`` at zero plastic strain."""

        if not np.isfinite(sigma_yield) or sigma_yield <= 0.0:
            raise ValueError("sigma_yield must be finite and positive")
        if not np.isfinite(K) or K <= 0.0:
            raise ValueError("K must be finite and positive")
        if not np.isfinite(n) or not (0.0 < n < 1.0):
            raise ValueError("require 0 < n < 1")
        if sigma_yield > K:
            raise ValueError(
                f"sigma_yield {sigma_yield:g} exceeds K {K:g}, so no eps_0 in (0, 1] exists; "
                "K is the flow stress where eps_0 + eps_p reaches unity and must be the larger of the two"
            )
        return cls(K=float(K), n=float(n), eps_0=float((sigma_yield / K) ** (1.0 / n)))

    @property
    def initial_yield_stress(self) -> float:
        """The flow stress at zero plastic strain."""

        return float(self.K) * float(self.eps_0) ** float(self.n)

    def flow_stress(self, eps_p: np.ndarray) -> np.ndarray:
        base = _plastic_strain(eps_p) + float(self.eps_0)
        return float(self.K) * np.power(base, float(self.n))

    def hardening_modulus(self, eps_p: np.ndarray) -> np.ndarray:
        base = _plastic_strain(eps_p) + float(self.eps_0)
        return float(self.K) * float(self.n) * np.power(base, float(self.n) - 1.0)


@dataclass(frozen=True)
class DNVC208MaterialCurve:
    """DNV-RP-C208 stepwise-linear plus power-law flow curve.

    Implements the DNV-RP-C208 (September 2019, amended October 2022) section
    4.6.6 recommendation.  The flow stress is a function of true plastic strain
    built from a stepwise linear part with a yield plateau and a power-law part:

        Part 1:  sigma_prop  -> sigma_yield    over  0        .. eps_p_y1
        Part 2:  sigma_yield -> sigma_yield_2  over  eps_p_y1 .. eps_p_y2
        Part 3:  sigma = K * (eps_p + (sigma_yield_2 / K)**(1/n) - eps_p_y2)**n

    The curve is expressed in true stress and true plastic strain exactly as
    tabulated by the recommended practice, so a consumer uses it directly as the
    flow stress without a conversion step of its own.
    """

    sigma_prop: float
    sigma_yield: float
    sigma_yield_2: float
    eps_p_y1: float
    eps_p_y2: float
    K: float
    n: float

    def __post_init__(self) -> None:
        if self.sigma_prop <= 0.0:
            raise ValueError("sigma_prop must be positive")
        if self.sigma_yield < self.sigma_prop:
            raise ValueError("sigma_yield must be >= sigma_prop")
        if self.sigma_yield_2 < self.sigma_yield:
            raise ValueError("sigma_yield_2 must be >= sigma_yield")
        if not (0.0 < self.eps_p_y1 < self.eps_p_y2):
            raise ValueError("require 0 < eps_p_y1 < eps_p_y2")
        if self.K <= 0.0 or not (0.0 < self.n < 1.0):
            raise ValueError("require K > 0 and 0 < n < 1")

    @property
    def _power_offset(self) -> float:
        """Plastic-strain offset making Part 3 continuous at eps_p_y2."""

        return (self.sigma_yield_2 / self.K) ** (1.0 / self.n) - self.eps_p_y2

    def flow_stress(self, eps_p: np.ndarray) -> np.ndarray:
        """Flow (yield) stress as a function of equivalent plastic strain."""

        eps_p = _plastic_strain(eps_p)
        slope_1 = (self.sigma_yield - self.sigma_prop) / self.eps_p_y1
        slope_2 = (self.sigma_yield_2 - self.sigma_yield) / (self.eps_p_y2 - self.eps_p_y1)
        part_1 = self.sigma_prop + slope_1 * eps_p
        part_2 = self.sigma_yield + slope_2 * (eps_p - self.eps_p_y1)
        part_3 = self.K * np.power(np.maximum(eps_p + self._power_offset, 1.0e-12), self.n)
        return np.where(
            eps_p <= self.eps_p_y1,
            part_1,
            np.where(eps_p <= self.eps_p_y2, part_2, part_3),
        )

    def hardening_modulus(self, eps_p: np.ndarray) -> np.ndarray:
        """d(flow stress)/d(equivalent plastic strain)."""

        eps_p = _plastic_strain(eps_p)
        slope_1 = (self.sigma_yield - self.sigma_prop) / self.eps_p_y1
        slope_2 = (self.sigma_yield_2 - self.sigma_yield) / (self.eps_p_y2 - self.eps_p_y1)
        base = np.maximum(eps_p + self._power_offset, 1.0e-12)
        slope_3 = self.K * self.n * np.power(base, self.n - 1.0)
        return np.where(
            eps_p <= self.eps_p_y1,
            slope_1,
            np.where(eps_p <= self.eps_p_y2, slope_2, slope_3),
        )

    def as_dict(self) -> Dict[str, float]:
        """Return a JSON-safe mapping of the seven curve parameters."""

        return {
            "sigma_prop": float(self.sigma_prop),
            "sigma_yield": float(self.sigma_yield),
            "sigma_yield_2": float(self.sigma_yield_2),
            "eps_p_y1": float(self.eps_p_y1),
            "eps_p_y2": float(self.eps_p_y2),
            "K": float(self.K),
            "n": float(self.n),
        }


def curve_from_properties(properties: Mapping[str, Any]) -> DNVC208MaterialCurve:
    """Build a curve from an RP-C208 table row (e.g. Table 4-2 .. 4-6)."""

    return DNVC208MaterialCurve(
        sigma_prop=float(properties["sigma_prop"]),
        sigma_yield=float(properties["sigma_yield"]),
        sigma_yield_2=float(properties["sigma_yield_2"]),
        eps_p_y1=float(properties.get("eps_p_y1", 0.004)),
        eps_p_y2=float(properties["eps_p_y2"]),
        K=float(properties["K"]),
        n=float(properties["n"]),
    )
