"""Download-only (no parsing) re-fetch of BTCUSDT monthly aggTrades zips,
retained on disk under data/raw_retained/, so the sensitivity grid's
Delta=10 and 3-minute-bar configs (preregistration section 8) can be
computed later without a second full re-download. Checksums are still
verified and recorded in the manifest; this does not touch data/staging
or data/parquet.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderflow import etl  # noqa: E402
from orderflow.config import STUDY_END, STUDY_START  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RETAIN_DIR = DATA_DIR / "raw_retained" / "BTCUSDT" / "aggTrades"
MANIFEST_PATH = DATA_DIR / "manifest.json"


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


def run() -> None:
    manifest = etl.Manifest.load(MANIFEST_PATH)
    months = list(month_range(STUDY_START, STUDY_END))
    log(f"Retaining BTCUSDT monthly aggTrades zips for {len(months)} months -> {RETAIN_DIR}")
    for year, month in months:
        url = etl.month_url("aggTrades", "BTCUSDT", year, month)
        dest = RETAIN_DIR / f"{year:04d}-{month:02d}.zip"
        if dest.exists():
            log(f"  {year:04d}-{month:02d}: already retained, skipping")
            continue
        try:
            zip_path = etl.download_and_verify(url, RETAIN_DIR, manifest)
            if zip_path is None:
                log(f"  {year:04d}-{month:02d}: not found remotely")
                continue
            if zip_path.name != dest.name:
                zip_path.rename(dest)
            log(f"  {year:04d}-{month:02d}: retained ({dest.stat().st_size/1e6:.1f} MB)")
        except Exception as exc:  # noqa: BLE001
            log(f"  {year:04d}-{month:02d}: ERROR {exc}")
    log("BTC raw-retention download complete.")


if __name__ == "__main__":
    run()
