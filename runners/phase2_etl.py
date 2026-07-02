"""Phase 2 ETL: full download + ingest + parquet bar store for BTCUSDT and
ETHUSDT, per preregistration/PREREGISTRATION.md section 1 and docs/BRIEF.md
section 2.4.

Resumable: each (symbol, year, month) is staged to its own small parquet
pair under data/staging/ immediately after processing, and raw zip/csv are
only deleted after the stage write succeeds. Re-running skips any month
that already has a staged file. The final continuous bar/bucket store
(with forward-fill, bar_index, cumulative_delta) is rebuilt from all staged
months every run, which is cheap (a few million rows).
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import etl, footprint, qa  # noqa: E402
from orderflow.config import BOOKDEPTH_START, DELTA, STUDY_END, STUDY_START, SYMBOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
PARQUET_DIR = DATA_DIR / "parquet"
MANIFEST_PATH = DATA_DIR / "manifest.json"
QA_LOG_PATH = DATA_DIR / "qa_ingest_log.jsonl"


def month_range(start: "object", end: "object"):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def stage_month_aggtrades(symbol: str, year: int, month: int, delta: float, manifest: etl.Manifest) -> bool:
    """Returns True if this month is staged (either just now or already
    present from a prior run), False if the month is missing from the
    remote archive entirely."""
    bars_path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_bars.parquet"
    buckets_path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_buckets.parquet"
    if bars_path.exists() and buckets_path.exists():
        return True

    url = etl.month_url("aggTrades", symbol, year, month)
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "aggTrades", manifest)
    if zip_path is None:
        log(f"  {symbol} {year:04d}-{month:02d} aggTrades: not found remotely, skipping")
        return False

    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "aggTrades_extracted")
    trades = etl.read_aggtrades(csv_path)

    # gap scan + intraday monotonicity, per docs/BRIEF.md section 2.2 - must
    # happen now, before raw ticks are discarded below.
    qa_record = qa.log_month_qa(QA_LOG_PATH, symbol, year, month, trades)
    if qa_record["missing_days"]:
        log(
            f"  {symbol} {year:04d}-{month:02d}: monthly archive missing days "
            f"{qa_record['missing_days']}, backfilling from daily archive"
        )
        trades, still_missing = etl.backfill_missing_days(
            trades, symbol, year, month, qa_record["missing_days"], RAW_DIR / symbol, manifest
        )
        if still_missing:
            log(f"  {symbol} {year:04d}-{month:02d}: GENUINE GAP - daily archive also missing {still_missing}")
        else:
            log(f"  {symbol} {year:04d}-{month:02d}: backfill recovered all missing days ({trades.height:,} trades now)")
    elif not qa_record["raw_order_monotonic"]:
        log(f"  {symbol} {year:04d}-{month:02d}: raw file not time-ordered (re-sorted defensively, no data loss)")

    bars, buckets = footprint.aggregate_month(trades, delta=delta)

    bars_path.parent.mkdir(parents=True, exist_ok=True)
    bars.write_parquet(bars_path)
    buckets.write_parquet(buckets_path)

    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)
    log(f"  {symbol} {year:04d}-{month:02d} aggTrades: staged ({trades.height:,} trades -> {bars.height} bars, {buckets.height} buckets)")
    return True


def stage_month_klines(symbol: str, year: int, month: int, manifest: etl.Manifest) -> None:
    path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_klines.parquet"
    if path.exists():
        return
    url = etl.month_url("klines", symbol, year, month, sub="1m")
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "klines", manifest)
    if zip_path is None:
        return
    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "klines_extracted")
    kl = etl.read_klines(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    kl.write_parquet(path)
    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)


def stage_month_fundingrate(symbol: str, year: int, month: int, manifest: etl.Manifest) -> None:
    path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_fundingRate.parquet"
    if path.exists():
        return
    url = etl.month_url("fundingRate", symbol, year, month)
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "fundingRate", manifest)
    if zip_path is None:
        return
    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "fundingRate_extracted")
    fr = etl.read_fundingrate(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fr.write_parquet(path)
    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)


def stage_day_bookdepth(symbol: str, date, manifest: etl.Manifest) -> None:
    path = STAGING_DIR / symbol / "bookDepth" / f"{date.isoformat()}.parquet"
    if path.exists():
        return
    url = etl.day_url("bookDepth", symbol, date)
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "bookDepth", manifest)
    if zip_path is None:
        return
    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "bookDepth_extracted")
    bd = etl.read_bookdepth(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bd.write_parquet(path)
    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)


def finalize_symbol(symbol: str, delta: float) -> None:
    bar_files = sorted((STAGING_DIR / symbol).glob("*_bars.parquet"))
    bucket_files = sorted((STAGING_DIR / symbol).glob("*_buckets.parquet"))
    if not bar_files:
        log(f"  {symbol}: no staged months found, skipping finalize")
        return
    partial_bars = pl.concat([pl.read_parquet(f) for f in bar_files])
    partial_buckets = pl.concat([pl.read_parquet(f) for f in bucket_files])

    full_bars = footprint.finalize_symbol_bars(partial_bars, STUDY_START, STUDY_END)
    full_buckets = footprint.finalize_symbol_buckets(partial_buckets, full_bars)

    out_dir = PARQUET_DIR / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    full_bars.write_parquet(out_dir / "bars.parquet")
    full_buckets.write_parquet(out_dir / "buckets.parquet")
    log(f"  {symbol}: finalized {full_bars.height:,} bars, {full_buckets.height:,} buckets -> {out_dir}")


def run(symbols=SYMBOLS, include_bookdepth_btc=True) -> None:
    manifest = etl.Manifest.load(MANIFEST_PATH)
    months = list(month_range(STUDY_START, STUDY_END))
    log(f"Study period: {STUDY_START.date()} to {STUDY_END.date()} ({len(months)} months)")

    for symbol in symbols:
        delta = DELTA[symbol]
        log(f"=== {symbol} (delta={delta}) ===")
        for year, month in months:
            for attempt in range(3):
                try:
                    stage_month_aggtrades(symbol, year, month, delta, manifest)
                    stage_month_klines(symbol, year, month, manifest)
                    stage_month_fundingrate(symbol, year, month, manifest)
                    break
                except Exception:  # noqa: BLE001
                    log(f"  ERROR on {symbol} {year:04d}-{month:02d} (attempt {attempt+1}/3):")
                    traceback.print_exc()
                    time.sleep(5)
            else:
                log(f"  GIVING UP on {symbol} {year:04d}-{month:02d} after 3 attempts")

        finalize_symbol(symbol, delta)

    if include_bookdepth_btc:
        log("=== BTCUSDT bookDepth (daily, 2023-01-01 onward, descriptive only) ===")
        import datetime as dt

        d = BOOKDEPTH_START.date()
        end_d = STUDY_END.date()
        n_days = (end_d - d).days + 1
        for i in range(n_days):
            date = d + dt.timedelta(days=i)
            try:
                stage_day_bookdepth("BTCUSDT", date, manifest)
            except Exception:  # noqa: BLE001
                log(f"  ERROR on bookDepth {date}:")
                traceback.print_exc()
            if i % 60 == 0:
                log(f"  bookDepth progress: {i}/{n_days} days")

    log("Phase 2 ETL run complete.")


if __name__ == "__main__":
    run()
