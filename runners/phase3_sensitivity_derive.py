"""Derive the two sensitivity-grid configs that CAN be built from the
primary 5m/Delta=25 BTC store by pure aggregation (preregistration section
8): Delta=50 (bar=5m) and bar=15m (Delta=25). BTC in-sample only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import footprint  # noqa: E402
from orderflow.config import IS_END, IS_START  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_DIR = ROOT / "data" / "parquet" / "BTCUSDT"
OUT_DIR = ROOT / "data" / "parquet_sensitivity"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run() -> None:
    log("Loading primary BTC store and slicing to IS period...")
    bars = pl.read_parquet(PRIMARY_DIR / "bars.parquet")
    buckets = pl.read_parquet(PRIMARY_DIR / "buckets.parquet")

    is_start_ms = int(IS_START.timestamp() * 1000)
    is_end_ms = int(IS_END.timestamp() * 1000)
    is_bars = bars.filter((pl.col("bar_ts_ms") >= is_start_ms) & (pl.col("bar_ts_ms") <= is_end_ms))
    is_bucket_bar_ids = set(is_bars["bar_index"].to_list())
    is_buckets = buckets.filter(pl.col("bar_index").is_in(is_bucket_bar_ids))
    log(f"  IS slice: {is_bars.height:,} bars, {is_buckets.height:,} buckets")

    # Delta=50, bar=5m: bars unchanged, buckets re-aggregated
    delta50_buckets = footprint.rebucket(is_buckets, new_delta=50.0, old_delta=25.0)
    out_dir = OUT_DIR / "delta50_bar5m" / "BTCUSDT"
    out_dir.mkdir(parents=True, exist_ok=True)
    is_bars.write_parquet(out_dir / "bars.parquet")
    delta50_buckets.write_parquet(out_dir / "buckets.parquet")
    log(f"delta50_bar5m: {is_bars.height:,} bars, {delta50_buckets.height:,} buckets -> {out_dir}")

    # bar=15m, Delta=25: both bars and buckets regrouped
    new_bars, new_buckets = footprint.rebar(is_bars, is_buckets, new_bar_ms=15 * 60_000, old_bar_ms=5 * 60_000)
    out_dir = OUT_DIR / "bar15m_delta25" / "BTCUSDT"
    out_dir.mkdir(parents=True, exist_ok=True)
    new_bars.write_parquet(out_dir / "bars.parquet")
    new_buckets.write_parquet(out_dir / "buckets.parquet")
    log(f"bar15m_delta25: {new_bars.height:,} bars, {new_buckets.height:,} buckets -> {out_dir}")

    log("Derivation complete.")


if __name__ == "__main__":
    run()
