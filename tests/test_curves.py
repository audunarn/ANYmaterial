"""Hardening curves and the DNV-RP-C208 table.

The table tests are migrated from ``ANYsolver/tests/test_fe_solver_nonlinear_dnv.py``
and keep their literal expected values.  That is the point: the numbers are
transcribed from the recommended practice, so a test that recomputed them from
the data file would only prove the file was read, not that it was right.
"""

from __future__ import annotations

import numpy as np
import pytest

from anymaterial import (
    DNVC208MaterialCurve,
    HardeningCurve,
    LinearHardeningCurve,
    PiecewiseLinearCurve,
    PowerLawHardeningCurve,
    available_grades,
    curve_from_properties,
    dnv_c208_steel_curve,
    dnv_c208_steel_properties,
    steel,
    thickness_classes,
)


def test_dnv_c208_steel_curve_factory_matches_low_fractile_tables() -> None:
    s355 = dnv_c208_steel_curve("S355", 0.010)
    assert s355.sigma_prop == pytest.approx(320.0e6)
    assert s355.sigma_yield == pytest.approx(357.0e6)
    assert s355.sigma_yield_2 == pytest.approx(363.3e6)
    assert s355.eps_p_y1 == pytest.approx(0.004)
    assert s355.eps_p_y2 == pytest.approx(0.015)
    assert s355.K == pytest.approx(740.0e6)
    assert s355.n == pytest.approx(0.166)

    s420 = dnv_c208_steel_curve("S420", 0.020)
    assert s420.sigma_prop == pytest.approx(360.6e6)
    assert s420.sigma_yield == pytest.approx(402.4e6)
    assert s420.sigma_yield_2 == pytest.approx(407.3e6)
    assert s420.eps_p_y2 == pytest.approx(0.012)
    assert s420.K == pytest.approx(703.0e6)
    assert s420.n == pytest.approx(0.14)

    s460 = dnv_c208_steel_curve("S460", 0.050)
    assert s460.sigma_prop == pytest.approx(374.2e6)
    assert s460.sigma_yield == pytest.approx(417.5e6)
    assert s460.sigma_yield_2 == pytest.approx(421.2e6)

    with pytest.raises(NotImplementedError):
        dnv_c208_steel_curve("S355", 0.010, fractile="mean")


@pytest.mark.parametrize(
    ("grade", "maximum_thickness"),
    [
        ("S235", 0.100),
        ("S275", 0.063),
        ("S355", 0.100),
        ("S420", 0.063),
        ("S460", 0.063),
    ],
)
def test_dnv_c208_automatic_thickness_selection_fails_outside_grade_table(
    grade: str,
    maximum_thickness: float,
) -> None:
    with pytest.raises(ValueError, match="thickness must be positive"):
        dnv_c208_steel_properties(grade, 0.0)
    with pytest.raises(ValueError, match="outside the built-in RP-C208 range"):
        dnv_c208_steel_properties(grade, maximum_thickness + 0.001)
    # The boundary itself is inside the table: rows are `lower < t <= upper`.
    dnv_c208_steel_properties(grade, maximum_thickness)


def test_dnv_c208_validates_grade_and_explicit_thickness_class() -> None:
    with pytest.raises(ValueError, match="Unsupported RP-C208 steel grade"):
        dnv_c208_steel_properties("S500", 0.010)
    with pytest.raises(ValueError, match="Unsupported thickness_class"):
        dnv_c208_steel_properties("S355", 0.010, thickness_class="not-a-table-row")

    # An explicit class deliberately overrides the range check, so a documented
    # deviation is possible where an accident is not.
    selected = dnv_c208_steel_properties("s355", 0.200, thickness_class="40 < t <= 63")
    assert selected["grade"] == "S355"
    assert selected["thickness_class"] == "40 < t <= 63"
    assert selected["thickness_mm"] == pytest.approx(200.0)
    assert selected["sigma_yield"] == pytest.approx(336.9e6)


def test_grade_and_class_listing_matches_the_table() -> None:
    assert available_grades() == ("S235", "S275", "S355", "S420", "S460")
    assert thickness_classes("S355") == (
        "t <= 16",
        "16 < t <= 40",
        "40 < t <= 63",
        "63 < t <= 100",
    )
    assert thickness_classes("s275") == ("t <= 16", "16 < t <= 40", "40 < t <= 63")
    with pytest.raises(ValueError, match="Unsupported RP-C208 steel grade"):
        thickness_classes("S500")


def test_dnv_c208_row_is_reported_in_si_units() -> None:
    properties = dnv_c208_steel_properties("S355", 0.010)

    assert properties["E_pa"] == pytest.approx(210.0e9)
    assert properties["source"].startswith("DNV-RP-C208")
    # Tabulated in MPa, converted once at the data boundary.  A value below 1e6
    # would mean the conversion was skipped.
    assert float(properties["sigma_yield"]) > 1.0e6


def test_dnv_curve_is_continuous_across_its_three_parts() -> None:
    curve = dnv_c208_steel_curve("S355", 0.010)

    assert curve.flow_stress(np.array(0.0)) == pytest.approx(curve.sigma_prop)
    assert curve.flow_stress(np.array(curve.eps_p_y1)) == pytest.approx(curve.sigma_yield)
    assert curve.flow_stress(np.array(curve.eps_p_y2)) == pytest.approx(curve.sigma_yield_2)

    # Part 3 joins Part 2 at eps_p_y2 by construction of the power offset.
    just_after = curve.flow_stress(np.array(curve.eps_p_y2 + 1.0e-9))
    assert just_after == pytest.approx(curve.sigma_yield_2, rel=1.0e-6)

    strains = np.linspace(0.0, 0.2, 501)
    stresses = curve.flow_stress(strains)
    assert np.all(np.diff(stresses) >= -1.0e-6)
    assert np.all(curve.hardening_modulus(strains) > 0.0)


def test_dnv_curve_matches_a_numerical_derivative() -> None:
    curve = dnv_c208_steel_curve("S460", 0.010)
    # Sampled away from the two kinks, where the derivative is genuinely
    # discontinuous and a central difference has nothing to converge to.
    strains = np.array([0.001, 0.007, 0.03, 0.08])
    step = 1.0e-9
    numerical = (curve.flow_stress(strains + step) - curve.flow_stress(strains - step)) / (2.0 * step)

    assert curve.hardening_modulus(strains) == pytest.approx(numerical, rel=1.0e-4)


def test_dnv_curve_rejects_inconsistent_parameters() -> None:
    valid = dict(
        sigma_prop=320.0e6,
        sigma_yield=357.0e6,
        sigma_yield_2=363.3e6,
        eps_p_y1=0.004,
        eps_p_y2=0.015,
        K=740.0e6,
        n=0.166,
    )
    DNVC208MaterialCurve(**valid)

    with pytest.raises(ValueError, match="sigma_yield must be >= sigma_prop"):
        DNVC208MaterialCurve(**{**valid, "sigma_yield": 300.0e6})
    with pytest.raises(ValueError, match="sigma_yield_2 must be >= sigma_yield"):
        DNVC208MaterialCurve(**{**valid, "sigma_yield_2": 350.0e6})
    with pytest.raises(ValueError, match=r"0 < eps_p_y1 < eps_p_y2"):
        DNVC208MaterialCurve(**{**valid, "eps_p_y1": 0.02})
    with pytest.raises(ValueError, match="0 < n < 1"):
        DNVC208MaterialCurve(**{**valid, "n": 1.5})


def test_curve_from_properties_defaults_eps_p_y1() -> None:
    curve = curve_from_properties(
        {
            "sigma_prop": 320.0e6,
            "sigma_yield": 357.0e6,
            "sigma_yield_2": 363.3e6,
            "eps_p_y2": 0.015,
            "K": 740.0e6,
            "n": 0.166,
        }
    )
    assert curve.eps_p_y1 == pytest.approx(0.004)


def test_steel_factory_attaches_hardening_only_when_asked() -> None:
    elastic = steel("S355", 0.020)
    assert elastic.name == "S355"
    assert elastic.elastic_modulus == pytest.approx(210.0e9)
    assert elastic.poisson_ratio == pytest.approx(0.3)
    assert elastic.density == pytest.approx(7850.0)
    assert elastic.yield_stress == pytest.approx(346.9e6)
    assert not elastic.is_nonlinear

    plastic = steel("S355", 0.020, name="deck", nonlinear=True)
    assert plastic.name == "deck"
    assert plastic.is_nonlinear
    assert plastic.hardening_curve.sigma_yield == pytest.approx(346.9e6)


@pytest.mark.parametrize(
    "curve",
    [
        LinearHardeningCurve(355.0e6, 2000.0e6),
        LinearHardeningCurve(355.0e6),
        PiecewiseLinearCurve.from_points([(0.0, 355.0e6), (0.02, 400.0e6), (0.1, 450.0e6)]),
        PowerLawHardeningCurve.from_yield(355.0e6, 740.0e6, 0.166),
        DNVC208MaterialCurve(320.0e6, 357.0e6, 363.3e6, 0.004, 0.015, 740.0e6, 0.166),
    ],
)
def test_every_curve_satisfies_the_protocol_and_vectorizes(curve: HardeningCurve) -> None:
    assert isinstance(curve, HardeningCurve)

    strains = np.linspace(0.0, 0.15, 36)
    stresses = np.asarray(curve.flow_stress(strains), dtype=float)
    moduli = np.asarray(curve.hardening_modulus(strains), dtype=float)

    assert stresses.shape == strains.shape
    assert moduli.shape == strains.shape
    assert np.all(np.isfinite(stresses)) and np.all(stresses > 0.0)
    assert np.all(np.isfinite(moduli)) and np.all(moduli >= 0.0)

    # Negative plastic strain is round-off in a return mapping, and is clamped
    # rather than producing a stress below the initial yield.
    assert curve.flow_stress(np.array(-1.0e-12)) == pytest.approx(curve.flow_stress(np.array(0.0)))

    # A field of integration points is evaluated in one call.
    field = np.zeros((4, 5))
    assert np.asarray(curve.flow_stress(field)).shape == (4, 5)


def test_linear_hardening_is_exactly_bilinear() -> None:
    curve = LinearHardeningCurve(355.0e6, 2000.0e6)
    strains = np.array([0.0, 0.01, 0.05])

    assert curve.flow_stress(strains) == pytest.approx(355.0e6 + 2000.0e6 * strains)
    assert curve.hardening_modulus(strains) == pytest.approx(np.full(3, 2000.0e6))

    perfect = LinearHardeningCurve(355.0e6)
    assert perfect.flow_stress(strains) == pytest.approx(np.full(3, 355.0e6))
    assert perfect.hardening_modulus(strains) == pytest.approx(np.zeros(3))

    with pytest.raises(ValueError, match="finite and positive"):
        LinearHardeningCurve(0.0)
    with pytest.raises(ValueError, match="must not be negative"):
        LinearHardeningCurve(355.0e6, -1.0)


def test_piecewise_linear_interpolates_and_then_holds() -> None:
    curve = PiecewiseLinearCurve.from_points([(0.0, 300.0e6), (0.02, 400.0e6), (0.10, 440.0e6)])

    assert curve.flow_stress(np.array(0.0)) == pytest.approx(300.0e6)
    assert curve.flow_stress(np.array(0.01)) == pytest.approx(350.0e6)
    assert curve.flow_stress(np.array(0.02)) == pytest.approx(400.0e6)
    assert curve.flow_stress(np.array(0.06)) == pytest.approx(420.0e6)
    # Perfectly plastic past the table rather than extrapolated: the curve does
    # not invent strength that was never measured.
    assert curve.flow_stress(np.array(0.5)) == pytest.approx(440.0e6)

    assert curve.hardening_modulus(np.array(0.01)) == pytest.approx(5.0e9)
    assert curve.hardening_modulus(np.array(0.05)) == pytest.approx(0.5e9)
    assert curve.hardening_modulus(np.array(0.5)) == pytest.approx(0.0)


def test_piecewise_linear_rejects_unusable_tables() -> None:
    with pytest.raises(ValueError, match="at least two points"):
        PiecewiseLinearCurve.from_points([(0.0, 300.0e6)])
    with pytest.raises(ValueError, match="must start at 0.0"):
        PiecewiseLinearCurve.from_points([(0.001, 300.0e6), (0.02, 400.0e6)])
    with pytest.raises(ValueError, match="strictly increasing"):
        PiecewiseLinearCurve.from_points([(0.0, 300.0e6), (0.0, 400.0e6)])
    with pytest.raises(ValueError, match="must be positive"):
        PiecewiseLinearCurve.from_points([(0.0, 0.0), (0.02, 400.0e6)])
    with pytest.raises(ValueError, match="must not decrease"):
        PiecewiseLinearCurve.from_points([(0.0, 400.0e6), (0.02, 300.0e6)])
    with pytest.raises(ValueError, match="equal length"):
        PiecewiseLinearCurve(plastic_strain=(0.0, 0.01), flow_stress_values=(300.0e6,))


def test_power_law_starts_exactly_at_the_yield_stress() -> None:
    curve = PowerLawHardeningCurve.from_yield(355.0e6, 740.0e6, 0.166)

    assert curve.initial_yield_stress == pytest.approx(355.0e6)
    assert curve.flow_stress(np.array(0.0)) == pytest.approx(355.0e6)
    # K is the flow stress where the argument reaches unity, which is at
    # eps_p = 1 - eps_0 rather than at eps_p = 1.
    assert curve.flow_stress(np.array(1.0 - curve.eps_0)) == pytest.approx(740.0e6)

    strains = np.array([0.002, 0.02, 0.09])
    step = 1.0e-10
    numerical = (curve.flow_stress(strains + step) - curve.flow_stress(strains - step)) / (2.0 * step)
    assert curve.hardening_modulus(strains) == pytest.approx(numerical, rel=1.0e-4)

    with pytest.raises(ValueError, match="exceeds K"):
        PowerLawHardeningCurve.from_yield(800.0e6, 740.0e6, 0.166)
    with pytest.raises(ValueError, match="eps_0 must be finite and positive"):
        PowerLawHardeningCurve(K=740.0e6, n=0.166, eps_0=0.0)
