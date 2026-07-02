"""Stage the two sensitivity-grid configs that cannot be derived from the
primary 5m/Delta=25 store (preregistration section 8): Delta=10 (bar=5m)
and bar=3m (Delta=25). BTC in-sample only (2022-07-01 to 2024-12-31).

Uses the BTCUSDT monthly aggTrades zips already retained under
data/raw_retained/ during the QA phase - no re-download.
"""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import etl, footprint  # noqa: E402
from orderflow.config import IS_END, IS_START  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RETAIN_DIR = ROOT / "data" / "raw_retained" / "BTCUSDT" / "aggTrades"
OUT_DIR = ROOT / "data" / "parquet_sensitivity"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
SYMBOL = "BTCUSDT"

# Known monthly-archive gaps within the IS period (from data/qa_ingest_log.jsonl,
# Phase 2 QA) - the raw_retained zips are the ORIGINAL monthly files, not the
# QA-repaired ones the primary store uses. Applying the same backfill here
# keeps all four sensitivity configs built from equally-complete data, so
# "one factor at a time" only ever varies the factor under test, never data
# completeness alongside it.
KNOWN_GAPS = {
    (2022, 8): [28, 29, 30],
    (2022, 9): [1, 10],
    (2022, 10): [29],
    (2022, 11): [7, 14],
    (2023, 5): [9],
}

CONFIGS = {
    "delta10_bar5m": {"delta": 10.0, "bar_ms": 5 * 60_000},
    "bar3m_delta25": {"delta": 25.0, "bar_ms": 3 * 60_000},
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def month_range(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def extract_from_retained(year: int, month: int, tmp_dir: Path) -> Path | None:
    zip_path = RETAIN_DIR / f"{year:04d}-{month:02d}.zip"
    if not zip_path.exists():
        log(f"  {year:04d}-{month:02d}: not found in raw_retained, skipping")
        return None
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert len(names) == 1, names
        zf.extract(names[0], tmp_dir)
        return tmp_dir / names[0]


def run() -> None:
    months = list(month_range(IS_START, IS_END))
    log(f"Staging {len(CONFIGS)} sensitivity configs over {len(months)} IS months from data/raw_retained/")

    partials = {name: {"bars": [], "buckets": []} for name in CONFIGS}
    tmp_dir = ROOT / "data" / "raw" / "BTCUSDT" / "sensitivity_extract"
    manifest = etl.Manifest.load(MANIFEST_PATH)

    for year, month in months:
        csv_path = extract_from_retained(year, month, tmp_dir)
        if csv_path is None:
            continue
        trades = etl.read_aggtrades(csv_path)
        gap_days = KNOWN_GAPS.get((year, month))
        if gap_days:
            trades, still_missing = etl.backfill_missing_days(trades, SYMBOL, year, month, gap_days, ROOT / "data" / "raw" / SYMBOL, manifest)
            log(f"  {year:04d}-{month:02d}: applied known backfill for days {gap_days} (still_missing={still_missing})")
        for name, cfg in CONFIGS.items():
            bars, buckets = footprint.aggregate_month(trades, delta=cfg["delta"], bar_ms=cfg["bar_ms"])
            partials[name]["bars"].append(bars)
            partials[name]["buckets"].append(buckets)
        csv_path.unlink(missing_ok=True)
        log(f"  {year:04d}-{month:02d}: staged ({trades.height:,} trades) for all configs")

    for name, cfg in CONFIGS.items():
        all_bars = pl.concat(partials[name]["bars"])
        all_buckets = pl.concat(partials[name]["buckets"])
        full_bars = footprint.finalize_symbol_bars(all_bars, IS_START, IS_END, bar_ms=cfg["bar_ms"])
        full_buckets = footprint.finalize_symbol_buckets(all_buckets, full_bars)

        out_dir = OUT_DIR / name / SYMBOL
        out_dir.mkdir(parents=True, exist_ok=True)
        full_bars.write_parquet(out_dir / "bars.parquet")
        full_buckets.write_parquet(out_dir / "buckets.parquet")
        log(f"{name}: {full_bars.height:,} bars, {full_buckets.height:,} buckets -> {out_dir}")

    log("Sensitivity staging complete.")


if __name__ == "__main__":
    run()
