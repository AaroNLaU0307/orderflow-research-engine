"""One-off: pull daily klines for 2026-06 (both symbols) since the monthly
klines archive for that month is not yet published (aggTrades monthly IS
published - an archive-publishing-lag artifact, confirmed in QA). Stages
them into a single combined parquet matching the normal monthly-klines
staging shape, so the reconciliation runner picks it up unchanged.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import etl  # noqa: E402
from orderflow.config import SYMBOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def run() -> None:
    manifest = etl.Manifest.load(MANIFEST_PATH)
    for symbol in SYMBOLS:
        frames = []
        for day in range(1, 31):
            date = dt.date(2026, 6, day)
            url = etl.day_url("klines", symbol, date, sub="1m")
            zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "klines_daily_202606", manifest)
            if zip_path is None:
                print(f"{symbol} {date}: not available")
                continue
            csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "klines_daily_202606_extracted")
            kl = etl.read_klines(csv_path)
            frames.append(kl)
            zip_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)
        combined = pl.concat(frames)
        out_path = STAGING_DIR / symbol / "2026-06_klines.parquet"
        combined.write_parquet(out_path)
        print(f"{symbol}: {combined.height} rows -> {out_path}")


if __name__ == "__main__":
    run()
