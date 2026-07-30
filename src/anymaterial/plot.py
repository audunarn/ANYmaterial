"""Plotting flow curves, as SVG.

Written by hand rather than through matplotlib so that plotting a curve costs no
dependency.  A material library whose only way to show a curve pulled in a
plotting stack would be a library people avoided importing.

SVG because it is text: it goes in a report, a commit, or a web page without a
rasterisation step, and it stays legible when someone opens it in an editor to
see what the numbers were.

Curves are drawn in **true stress against true plastic strain**, which is what
they are defined in.  Labelling the axes as engineering values would be a
different curve, and the difference matters exactly where plasticity is
interesting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import numpy as np

__all__ = ["CurveSeries", "curve_svg", "sample_curve", "write_curve_svg"]

# Enough to look smooth without making a file nobody wants to open.
DEFAULT_SAMPLES = 201
DEFAULT_MAX_STRAIN = 0.10

# Colour-blind-safe, and distinguishable in greyscale by order.
_PALETTE = (
    "#1a5fb4",
    "#c04000",
    "#26794f",
    "#8a4fbf",
    "#a08000",
    "#00808c",
    "#b03060",
    "#505050",
)

_MPA = 1.0e6


@dataclass(frozen=True)
class CurveSeries:
    """One curve on a plot."""

    label: str
    plastic_strain: Tuple[float, ...]
    flow_stress: Tuple[float, ...]

    @property
    def max_stress(self) -> float:
        return max(self.flow_stress) if self.flow_stress else 0.0


def sample_curve(
    curve: Any,
    label: str,
    *,
    max_strain: float = DEFAULT_MAX_STRAIN,
    samples: int = DEFAULT_SAMPLES,
) -> CurveSeries:
    """Sample a hardening curve into a plottable series."""

    if float(max_strain) <= 0.0:
        raise ValueError("max_strain must be positive")
    if int(samples) < 2:
        raise ValueError("a curve needs at least two samples")
    strains = np.linspace(0.0, float(max_strain), int(samples))
    stresses = np.asarray(curve.flow_stress(strains), dtype=float)
    if stresses.shape != strains.shape:
        raise ValueError(f"curve {label!r} did not return one flow stress per strain")
    return CurveSeries(
        label=label,
        plastic_strain=tuple(float(value) for value in strains),
        flow_stress=tuple(float(value) for value in stresses),
    )


def _nice_ceiling(value: float) -> float:
    """Round a value up to 1, 2 or 5 times a power of ten."""

    if value <= 0.0:
        return 1.0
    exponent = np.floor(np.log10(value))
    base = 10.0**exponent
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if value <= step * base:
            return step * base
    return 10.0 * base


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def curve_svg(
    series: Sequence[CurveSeries],
    *,
    title: str = "Flow curves",
    width: int = 720,
    height: int = 440,
    stress_unit: str = "MPa",
) -> str:
    """Render curves as a standalone SVG document."""

    series = list(series)
    if not series:
        raise ValueError("nothing to plot")

    left, right, top, bottom = 74, 210, 44, 56
    plot_width = max(width - left - right, 50)
    plot_height = max(height - top - bottom, 50)

    max_strain = max(max(item.plastic_strain) for item in series)
    max_stress = max(item.max_stress for item in series) / _MPA
    strain_limit = max(max_strain, 1.0e-9)
    stress_limit = _nice_ceiling(max_stress * 1.05)

    def x_of(strain: float) -> float:
        return left + plot_width * float(strain) / strain_limit

    def y_of(stress_pa: float) -> float:
        return top + plot_height * (1.0 - (float(stress_pa) / _MPA) / stress_limit)

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{left}" y="24" font-size="15" font-weight="600">{_escape(title)}</text>',
    ]

    # Gridlines first, so the curves sit on top of them.
    for index in range(6):
        stress = stress_limit * index / 5.0
        y = y_of(stress * _MPA)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
            f'stroke="#e0e0e0" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#404040">'
            f"{stress:g}</text>"
        )
        strain = strain_limit * index / 5.0
        x = x_of(strain)
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" '
            f'stroke="#f0f0f0" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_height + 18}" text-anchor="middle" fill="#404040">'
            f"{strain:.3f}</text>"
        )

    parts.append(
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
        f'fill="none" stroke="#606060" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{left + plot_width / 2:.0f}" y="{height - 14}" text-anchor="middle" '
        f'fill="#303030">true plastic strain [-]</text>'
    )
    parts.append(
        f'<text x="18" y="{top + plot_height / 2:.0f}" text-anchor="middle" fill="#303030" '
        f'transform="rotate(-90 18 {top + plot_height / 2:.0f})">'
        f"true stress [{_escape(stress_unit)}]</text>"
    )

    for index, item in enumerate(series):
        colour = _PALETTE[index % len(_PALETTE)]
        points = " ".join(
            f"{x_of(strain):.2f},{y_of(stress):.2f}"
            for strain, stress in zip(item.plastic_strain, item.flow_stress)
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="2"/>'
        )
        legend_y = top + 16 + index * 20
        parts.append(
            f'<line x1="{left + plot_width + 16}" y1="{legend_y}" '
            f'x2="{left + plot_width + 40}" y2="{legend_y}" stroke="{colour}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{left + plot_width + 46}" y="{legend_y + 4}" fill="#202020">'
            f"{_escape(item.label)}</text>"
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def write_curve_svg(
    path: str | Path,
    series: Sequence[CurveSeries],
    *,
    overwrite: bool = False,
    **options: Any,
) -> Path:
    """Write curves to an SVG file."""

    destination = Path(path)
    if destination.suffix.lower() != ".svg":
        destination = destination.with_suffix(".svg")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(curve_svg(series, **options), encoding="utf-8")
    return destination
