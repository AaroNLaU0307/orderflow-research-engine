"""Synthetic bar/bucket fixture builder for signal-detector tests.

Builds a controllable multi-week 5-minute bar series (numpy arrays, mutated
in place to inject deterministic triggers for each of H1/H2/H3/H6) plus a
matching footprint-bucket table, both already "finalized" in the same shape
`footprint.finalize_symbol_bars` / `finalize_symbol_buckets` would produce.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

DELTA = 25.0
BAR_MINUTES = 5
UTC = dt.timezone.utc


class FixtureBuilder:
    def __init__(self, n_bars: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.n_bars = n_bars
        self.rng = rng

        price_steps = rng.normal(0, 3.0, n_bars)
        close = 50_000 + np.cumsum(price_steps)
        open_ = np.empty(n_bars)
        open_[0] = close[0]
        open_[1:] = close[:-1]
        wick = np.abs(rng.normal(0, 1.0, n_bars)) * 2
        high = np.maximum(open_, close) + wick
        low = np.minimum(open_, close) - wick
        volume = rng.lognormal(mean=3.0, sigma=0.4, size=n_bars)
        delta = rng.normal(0, 2.0, n_bars)
        delta = np.clip(delta, -volume * 0.9, volume * 0.9)  # keep |delta|<volume (buy/sell split must stay non-negative)

        self.close = close
        self.open = open_
        self.high = high
        self.low = low
        self.volume = volume
        self.delta = delta
        self.bar_index = np.arange(n_bars)
        start = dt.datetime(2024, 1, 1, tzinfo=UTC)
        self.bar_ts = [start + dt.timedelta(minutes=BAR_MINUTES * i) for i in range(n_bars)]

        # bucket_rows[i] = list of (bucket_px, buy_vol, sell_vol); None = "use default single-bucket split"
        self.bucket_override: dict[int, list[tuple[float, float, float]]] = {}

    # ---- generic new-high / new-low anchor injection (see module docstring) ----
    def inject_clean_new_high(self, t: int, jump: float = 200.0, anchor_offset: float = 500.0) -> None:
        """Make close[t] an unambiguous fresh 24-bar high with no interference
        in [t-23, t-1] from earlier local structure."""
        anchor_idx = t - 24
        base_local = self.close[anchor_idx] if anchor_idx >= 0 else self.close[0]
        H = base_local + anchor_offset
        self.close[anchor_idx] = H
        self.open[anchor_idx] = H
        self.high[anchor_idx] = H + 1
        self.low[anchor_idx] = H - 1
        for i in range(t - 23, t):
            v = H - 50.0
            self.close[i] = v
            self.open[i] = v
            self.high[i] = v + 1
            self.low[i] = v - 1
        v = H + jump
        self.close[t] = v
        self.open[t] = H - 50.0
        self.high[t] = v + 1
        self.low[t] = v - 1

    def inject_clean_new_low(self, t: int, drop: float = 200.0, anchor_offset: float = 500.0) -> None:
        anchor_idx = t - 24
        base_local = self.close[anchor_idx] if anchor_idx >= 0 else self.close[0]
        L = base_local - anchor_offset
        self.close[anchor_idx] = L
        self.open[anchor_idx] = L
        self.high[anchor_idx] = L + 1
        self.low[anchor_idx] = L - 1
        for i in range(t - 23, t):
            v = L + 50.0
            self.close[i] = v
            self.open[i] = v
            self.high[i] = v + 1
            self.low[i] = v - 1
        v = L - drop
        self.close[t] = v
        self.open[t] = L + 50.0
        self.high[t] = v + 1
        self.low[t] = v - 1

    def set_delta_run(self, start_idx: int, length: int, delta_value: float, volume_value: float | None = None) -> None:
        for i in range(start_idx, start_idx + length):
            self.delta[i] = delta_value
            if volume_value is not None:
                self.volume[i] = volume_value
            else:
                self.volume[i] = max(abs(delta_value) * 1.1, self.volume[i])

    def override_buckets(self, t: int, rows: list[tuple[float, float, float]]) -> None:
        """rows: list of (bucket_px, buy_vol, sell_vol); replaces bar t's
        entire bucket set and keeps bar-level OHLCV/delta consistent."""
        self.bucket_override[t] = rows
        total_buy = sum(r[1] for r in rows)
        total_sell = sum(r[2] for r in rows)
        self.volume[t] = total_buy + total_sell
        self.delta[t] = total_buy - total_sell
        pxs = [r[0] for r in rows]
        self.low[t] = min(self.low[t], min(pxs))
        self.high[t] = max(self.high[t], max(pxs) + DELTA)

    def build(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        cumulative_delta = np.cumsum(self.delta)
        bars = pl.DataFrame(
            {
                "bar_index": self.bar_index,
                "bar_ts": self.bar_ts,
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
                "delta": self.delta,
                "cumulative_delta": cumulative_delta,
                "trade_count": np.maximum(self.volume.round().astype(int), 1),
            }
        )

        bucket_rows = []
        for i in range(self.n_bars):
            if i in self.bucket_override:
                for px, bv, sv in self.bucket_override[i]:
                    bucket_rows.append((i, self.bar_ts[i], px, bv, sv, 1))
                continue
            low_level = int(np.floor(self.low[i] / DELTA))
            high_level = int(np.floor(self.high[i] / DELTA))
            n_levels = max(1, high_level - low_level + 1)
            buy_total = max((self.volume[i] + self.delta[i]) / 2, 0.0)
            sell_total = max((self.volume[i] - self.delta[i]) / 2, 0.0)
            buy_split = self.rng.dirichlet(np.ones(n_levels)) * buy_total
            sell_split = self.rng.dirichlet(np.ones(n_levels)) * sell_total
            for k in range(n_levels):
                px = (low_level + k) * DELTA
                bv, sv = float(buy_split[k]), float(sell_split[k])
                if bv + sv <= 0:
                    continue
                bucket_rows.append((i, self.bar_ts[i], px, bv, sv, 1))

        buckets = pl.DataFrame(
            bucket_rows,
            schema=["bar_index", "bar_ts", "bucket_px", "buy_vol", "sell_vol", "trade_count"],
            orient="row",
        ).sort(["bar_index", "bucket_px"])
        return bars, buckets
