"""One-time repair pass for months staged by an earlier phase2_etl.py run
that predates the auto-backfill fix in stage_month_aggtrades. Scans
data/qa_ingest_log.jsonl for months with missing_days, re-fetches the
monthly zip + the missing days' daily zips, re-aggregates, and overwrites
that month's staged bars/buckets parquet. Idempotent: writes a repair
record to data/qa_backfill_log.jsonl and skips months already repaired
(matched by symbol/year/month AND the original missing_days list, so a
re-run after a fresh anomaly is still repaired).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderflow import etl, footprint  # noqa: E402
from orderflow.config import DELTA  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
MANIFEST_PATH = DATA_DIR / "manifest.json"
QA_LOG_PATH = DATA_DIR / "qa_ingest_log.jsonl"
BACKFILL_LOG_PATH = DATA_DIR / "qa_backfill_log.jsonl"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def already_repaired(repaired: list[dict], symbol: str, year: int, month: int, missing_days: list[int]) -> bool:
    for r in repaired:
        if (
            r["symbol"] == symbol
            and r["year"] == year
            and r["month"] == month
            and r["original_missing_days"] == missing_days
            and not r["still_missing"]
        ):
            return True
    return False


def repair_month(symbol: str, year: int, month: int, missing_days: list[int], manifest: etl.Manifest) -> dict:
    delta = DELTA[symbol]
    url = etl.month_url("aggTrades", symbol, year, month)
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "aggTrades", manifest)
    if zip_path is None:
        return {"error": "monthly file no longer available"}
    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "aggTrades_extracted")
    trades = etl.read_aggtrades(csv_path)

    trades, still_missing = etl.backfill_missing_days(trades, symbol, year, month, missing_days, RAW_DIR / symbol, manifest)

    bars, buckets = footprint.aggregate_month(trades, delta=delta)
    bars_path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_bars.parquet"
    buckets_path = STAGING_DIR / symbol / f"{year:04d}-{month:02d}_buckets.parquet"
    bars.write_parquet(bars_path)
    buckets.write_parquet(buckets_path)

    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)

    return {"n_trades": trades.height, "n_bars": bars.height, "still_missing": still_missing}


def run() -> None:
    manifest = etl.Manifest.load(MANIFEST_PATH)
    qa_records = load_jsonl(QA_LOG_PATH)
    repaired = load_jsonl(BACKFILL_LOG_PATH)

    flagged = [r for r in qa_records if r.get("missing_days")]
    log(f"Found {len(flagged)} month-records with missing_days in QA log ({len(qa_records)} total logged)")

    # de-dupe by (symbol,year,month) - a month may appear once per QA log write
    seen = set()
    unique_flagged = []
    for r in flagged:
        key = (r["symbol"], r["year"], r["month"])
        if key not in seen:
            seen.add(key)
            unique_flagged.append(r)

    for r in unique_flagged:
        symbol, year, month, missing_days = r["symbol"], r["year"], r["month"], r["missing_days"]
        if already_repaired(repaired, symbol, year, month, missing_days):
            log(f"  {symbol} {year:04d}-{month:02d}: already repaired, skipping")
            continue
        log(f"  {symbol} {year:04d}-{month:02d}: repairing (missing_days={missing_days})...")
        result = repair_month(symbol, year, month, missing_days, manifest)
        record = {
            "symbol": symbol,
            "year": year,
            "month": month,
            "original_missing_days": missing_days,
            "still_missing": result.get("still_missing", missing_days),
            "result": result,
        }
        with open(BACKFILL_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        if result.get("still_missing"):
            log(f"  {symbol} {year:04d}-{month:02d}: UNRECOVERABLE gap remains: {result['still_missing']}")
        else:
            log(f"  {symbol} {year:04d}-{month:02d}: repaired ({result.get('n_trades', '?'):,} trades)")

    log("Backfill repair pass complete.")


if __name__ == "__main__":
    run()
