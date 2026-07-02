"""Cost model. preregistration/PREREGISTRATION.md section 6.6.

Taker fee 5.0bp/side + slippage (half-spread, ~negligible for BTC, + 1.0bp
impact buffer)/side -> round trip ~=12bp. Funding: historical rate applied
to open notional at each funding timestamp crossed while a position is
open, signed by position side (longs pay when funding_rate > 0, matching
Binance mechanics).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from orderflow.config import IMPACT_BP, TAKER_FEE_BP

ROUND_TRIP_FRACTION = 2 * (TAKER_FEE_BP + IMPACT_BP) / 10_000.0  # e.g. 12bp -> 0.0012


def apply_entry_exit_costs(gross_return: np.ndarray) -> np.ndarray:
    """Net-of-fees-and-slippage return, before funding. gross_return is a
    signed log return; costs are subtracted as a simple (non-log) fractional
    drag, consistent with the prereg's basis-point framing of the round
    trip (~12bp applied once per round-trip trade, not per side compounded
    log-wise - the difference at these magnitudes is immaterial but the
    simple/linear form is what the prereg's "round trip ~=12bp" describes).
    """
    return gross_return - ROUND_TRIP_FRACTION


def funding_cost_for_position(
    position_side: int,
    entry_ms: int,
    exit_ms: int,
    funding_events_ms: np.ndarray,
    funding_rates: np.ndarray,
) -> float:
    """Sum of funding PnL (fractional, signed) for a position open from
    entry_ms (exclusive) to exit_ms (inclusive) - i.e. every funding
    timestamp strictly after entry and at or before exit is "crossed".
    funding_pnl = -position_side * funding_rate at each crossed timestamp
    (long pays when funding_rate > 0).
    """
    mask = (funding_events_ms > entry_ms) & (funding_events_ms <= exit_ms)
    if not mask.any():
        return 0.0
    return float(-position_side * funding_rates[mask].sum())


def funding_cost_for_events(
    position_side: np.ndarray,
    entry_ms: np.ndarray,
    exit_ms: np.ndarray,
    funding_events_ms: np.ndarray,
    funding_rates: np.ndarray,
) -> np.ndarray:
    """Vectorized funding cost across many events. For typical event
    horizons (<=4h) and funding cadence (8h), each event crosses at most
    one funding timestamp, but this makes no such assumption."""
    out = np.zeros(len(position_side))
    for i in range(len(position_side)):
        out[i] = funding_cost_for_position(
            int(position_side[i]), int(entry_ms[i]), int(exit_ms[i]), funding_events_ms, funding_rates
        )
    return out


def net_returns(
    gross_returns: np.ndarray,
    position_side: np.ndarray,
    entry_ms: np.ndarray,
    exit_ms: np.ndarray,
    funding_events_ms: np.ndarray,
    funding_rates: np.ndarray,
) -> np.ndarray:
    funding = funding_cost_for_events(position_side, entry_ms, exit_ms, funding_events_ms, funding_rates)
    return apply_entry_exit_costs(gross_returns) + funding


def load_funding_series(funding_df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """funding_df: the parsed fundingRate parquet (calc_time ms,
    funding_interval_hours, last_funding_rate). Returns (calc_time_ms
    array sorted, rate array aligned)."""
    sorted_df = funding_df.sort("calc_time")
    return sorted_df["calc_time"].to_numpy(), sorted_df["last_funding_rate"].to_numpy()
