"""Flow-curve plotting, as SVG."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from anymaterial import (
    CurveSeries,
    LinearHardeningCurve,
    PiecewiseLinearCurve,
    curve_svg,
    dnv_c208_steel_curve,
    library,
    sample_curve,
    write_curve_svg,
)


def _series(name: str = "S355") -> CurveSeries:
    return sample_curve(dnv_c208_steel_curve("S355", 0.010), name)


def test_sampling_a_curve_follows_the_curve() -> None:
    curve = dnv_c208_steel_curve("S355", 0.010)
    series = sample_curve(curve, "S355", max_strain=0.08, samples=41)

    assert series.label == "S355"
    assert len(series.plastic_strain) == len(series.flow_stress) == 41
    assert series.plastic_strain[0] == pytest.approx(0.0)
    assert series.plastic_strain[-1] == pytest.approx(0.08)
    # The plotted values are the curve's own, not a re-derivation of it.
    assert series.flow_stress[0] == pytest.approx(float(curve.flow_stress(np.array(0.0))))
    assert series.max_stress == pytest.approx(float(curve.flow_stress(np.array(0.08))))


def test_sampling_validates_its_range() -> None:
    curve = LinearHardeningCurve(355.0e6, 2000.0e6)

    with pytest.raises(ValueError, match="max_strain must be positive"):
        sample_curve(curve, "x", max_strain=0.0)
    with pytest.raises(ValueError, match="at least two samples"):
        sample_curve(curve, "x", samples=1)


def test_a_curve_that_does_not_vectorize_is_caught() -> None:
    class _Scalar:
        def flow_stress(self, eps_p):
            return 355.0e6  # not one value per strain

        def hardening_modulus(self, eps_p):
            return 0.0

    with pytest.raises(ValueError, match="one flow stress per strain"):
        sample_curve(_Scalar(), "scalar")


def test_the_svg_is_well_formed_and_self_contained() -> None:
    svg = curve_svg([_series()], title="One curve")

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.get("width") == "720"
    # No external references: the file stands alone in a report or a commit.
    assert "http://www.w3.org/2000/svg" in svg
    assert "<image" not in svg
    assert "xlink:href" not in svg


def test_every_curve_gets_a_polyline_and_a_legend_entry() -> None:
    catalogue = library()
    names = ["S235 (t <= 16 mm)", "S355 (t <= 16 mm)", "S460 (t <= 16 mm)"]
    series = [sample_curve(catalogue.get(name).spec.hardening_curve(), name) for name in names]

    svg = curve_svg(series, title="RP-C208 low fractile")

    assert svg.count("<polyline") == 3
    # Read the rendered text, not the markup: the labels contain "<=", which is
    # escaped on the way in and would not be found as a literal.
    rendered = {
        element.text
        for element in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text")
    }
    assert set(names) <= rendered
    # Distinct colours, or the legend cannot be matched to a line.
    colours = set(re.findall(r'<polyline[^>]*stroke="(#[0-9a-f]{6})"', svg))
    assert len(colours) == 3


def test_the_axes_are_labelled_as_true_values() -> None:
    svg = curve_svg([_series()])

    # Labelling these as engineering values would be a different curve, and the
    # difference matters exactly where plasticity is interesting.
    assert "true plastic strain" in svg
    assert "true stress [MPa]" in svg


def test_the_stress_axis_is_scaled_to_a_readable_ceiling() -> None:
    weak = sample_curve(LinearHardeningCurve(100.0e6), "weak")
    strong = sample_curve(LinearHardeningCurve(900.0e6), "strong")

    weak_svg = curve_svg([weak])
    strong_svg = curve_svg([strong])

    # Gridline labels come from a 1/2/2.5/5 x 10^n ceiling, so the axis never
    # reads 103.7 MPa.
    assert ">100<" in weak_svg or ">120<" in weak_svg
    assert ">1000<" in strong_svg


def test_a_label_with_markup_characters_is_escaped() -> None:
    series = CurveSeries(label='S355 <t & "x">', plastic_strain=(0.0, 0.1), flow_stress=(3.0e8, 4.0e8))

    svg = curve_svg([series])

    ET.fromstring(svg)  # would raise if the label broke the document
    assert "&lt;t &amp; &quot;x&quot;&gt;" in svg


def test_plotting_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing to plot"):
        curve_svg([])


def test_writing_adds_the_suffix_and_guards_overwriting(tmp_path) -> None:
    path = write_curve_svg(tmp_path / "curves", [_series()])

    assert path.suffix == ".svg"
    assert path.is_file()
    ET.fromstring(path.read_text(encoding="utf-8"))

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_curve_svg(path, [_series()])
    write_curve_svg(path, [_series()], overwrite=True)


def test_a_tabulated_curve_plots_its_flat_tail(tmp_path) -> None:
    curve = PiecewiseLinearCurve.from_points([(0.0, 300.0e6), (0.02, 400.0e6)])
    series = sample_curve(curve, "measured", max_strain=0.10, samples=51)

    # Perfectly plastic past the table, so the plotted tail is flat rather than
    # extrapolated.
    assert series.flow_stress[-1] == pytest.approx(400.0e6)
    assert series.flow_stress[-1] == pytest.approx(series.flow_stress[-2])
    ET.fromstring(curve_svg([series]))
