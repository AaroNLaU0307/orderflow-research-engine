import numpy as np
import pytest

from orderflow import costs


def test_round_trip_is_12bp():
    assert costs.ROUND_TRIP_FRACTION == pytest.approx(0.0012)


def test_apply_entry_exit_costs_subtracts_round_trip():
    gross = np.array([0.01, -0.005, 0.0])
    net = costs.apply_entry_exit_costs(gross)
    assert net == pytest.approx(gross - 0.0012)


def test_funding_cost_long_pays_positive_rate():
    funding_ms = np.array([1000, 2000, 3000])
    rates = np.array([0.0001, 0.0002, 0.0001])
    # long position open from before ts=1000 to after ts=2000 -> crosses 1000 and 2000
    cost = costs.funding_cost_for_position(1, entry_ms=500, exit_ms=2500, funding_events_ms=funding_ms, funding_rates=rates)
    assert cost == pytest.approx(-(0.0001 + 0.0002))  # long pays -> negative PnL


def test_funding_cost_short_receives_positive_rate():
    funding_ms = np.array([1000])
    rates = np.array([0.0001])
    cost = costs.funding_cost_for_position(-1, entry_ms=500, exit_ms=1500, funding_events_ms=funding_ms, funding_rates=rates)
    assert cost == pytest.approx(0.0001)  # short receives when rate > 0


def test_funding_cost_negative_rate_flips_sign():
    funding_ms = np.array([1000])
    rates = np.array([-0.0001])
    long_cost = costs.funding_cost_for_position(1, 500, 1500, funding_ms, rates)
    assert long_cost == pytest.approx(0.0001)  # long receives when rate < 0


def test_funding_cost_entry_exact_boundary_not_crossed():
    """entry_ms is exclusive: a funding event exactly at entry_ms is NOT
    crossed (position wasn't open yet at that instant)."""
    funding_ms = np.array([1000])
    rates = np.array([0.0001])
    cost = costs.funding_cost_for_position(1, entry_ms=1000, exit_ms=2000, funding_events_ms=funding_ms, funding_rates=rates)
    assert cost == 0.0


def test_funding_cost_exit_exact_boundary_is_crossed():
    funding_ms = np.array([1000])
    rates = np.array([0.0001])
    cost = costs.funding_cost_for_position(1, entry_ms=500, exit_ms=1000, funding_events_ms=funding_ms, funding_rates=rates)
    assert cost == pytest.approx(-0.0001)


def test_funding_cost_no_crossing_events():
    funding_ms = np.array([5000])
    rates = np.array([0.0001])
    cost = costs.funding_cost_for_position(1, entry_ms=1000, exit_ms=2000, funding_events_ms=funding_ms, funding_rates=rates)
    assert cost == 0.0


def test_net_returns_combines_costs_and_funding():
    gross = np.array([0.01])
    side = np.array([1])
    entry = np.array([500])
    exit_ = np.array([1500])
    funding_ms = np.array([1000])
    rates = np.array([0.0001])
    net = costs.net_returns(gross, side, entry, exit_, funding_ms, rates)
    expected = (0.01 - costs.ROUND_TRIP_FRACTION) - 0.0001
    assert net[0] == pytest.approx(expected)
