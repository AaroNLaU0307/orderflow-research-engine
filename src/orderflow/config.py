"""Frozen constants from preregistration/PREREGISTRATION.md. Do not tune these.

Any change requires a preregistration/DEVIATIONS.md entry (post-approval) or
falls outside the report-only sensitivity grid (section 8).
"""
from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc

STUDY_START = dt.datetime(2022, 7, 1, tzinfo=UTC)
STUDY_END = dt.datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC)
IS_START = STUDY_START
IS_END = dt.datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
OOS_START = dt.datetime(2025, 1, 1, tzinfo=UTC)
OOS_END = STUDY_END

# Year-consistency segments (section 6.4)
IS_SEGMENTS = {
    "2022H2": (dt.datetime(2022, 7, 1, tzinfo=UTC), dt.datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC)),
    "2023": (dt.datetime(2023, 1, 1, tzinfo=UTC), dt.datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC)),
    "2024": (dt.datetime(2024, 1, 1, tzinfo=UTC), dt.datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)),
}

BOOKDEPTH_START = dt.datetime(2023, 1, 1, tzinfo=UTC)  # archive coverage begins here (Phase 0 finding)

BAR_MINUTES = 5
BAR_MS = BAR_MINUTES * 60_000

DELTA = {"BTCUSDT": 25.0, "ETHUSDT": 1.0}

# section 8 sensitivity grid (report-only, never gating)
SENSITIVITY_DELTA = {"BTCUSDT": [10.0, 50.0]}
SENSITIVITY_BAR_MINUTES = [3, 15]

WARM_UP_BARS = 8640  # section 5: max lookback across signals (H1's 30-day sigma), corrected from brief's 2016
DEDUP_GAP_BARS = 6

HORIZONS_BARS = [1, 3, 6, 12, 48]  # 5m, 15m, 30m, 1h, 4h
MIN_MATERIAL_HORIZON_BARS = 6  # 30 minutes

H1_CUMDELTA_WINDOW = 24
H1_SIGMA_WINDOW = 8640  # 30 days
H2_ZONE_FRACTION = 0.20
H2_VOLUME_WINDOW = 96
H2_VOLUME_MULTIPLE = 4.0
H2_AGGRESSION_FRACTION = 0.70
H3_VOLUME_WINDOW = 96
H3_IMBALANCE_RATIO = 3.0
H3_MIN_STACK = 3
H6_VOLUME_WINDOW = 2016  # 1 week
H6_VOLUME_PCTL = 0.95
H24_HIGH_WINDOW = 24  # "24-bar high/low" used by H1 and H6

# section 6.6 cost model
TAKER_FEE_BP = 5.0
IMPACT_BP = 1.0
BTC_TICK = 0.1
ROUND_TRIP_BP = 2 * (TAKER_FEE_BP + IMPACT_BP)  # + half-spread, ~negligible for BTC; stated ~12bp in prereg

# section 6.5 gate 3
MATERIALITY_BP = 1.5 * ROUND_TRIP_BP  # ~18bp

# section 6.5 gate 1
MIN_EVENTS = 300

# section 6.3
FDR_Q = 0.10

BOOTSTRAP_REPS = 10_000

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
