"""Phase 2 QA suite (post-ingest): manifest completeness, full-period
aggTrades-vs-klines volume reconciliation, and a summary of the inline
gap/monotonicity findings logged during ingest (runners/phase2_etl.py).
Writes reports/QA_SUMMARY.md (runner-generated, immutable per repo rules).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import qa  # noqa: E402
from orderflow.config import BOOKDEPTH_START, DELTA, STUDY_END, STUDY_START, SYMBOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STAGING_DIR = DATA_DIR / "staging"
PARQUET_DIR = DATA_DIR / "parquet"
MANIFEST_PATH = DATA_DIR / "manifest.json"
QA_LOG_PATH = DATA_DIR / "qa_ingest_log.jsonl"
REPORT_PATH = ROOT / "reports" / "QA_SUMMARY.md"


def month_range(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def check_manifest_completeness() -> dict:
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    months = list(month_range(STUDY_START, STUDY_END))
    missing = []
    checksum_failures = []
    for symbol in SYMBOLS:
        for dataset in ["aggTrades", "klines", "fundingRate"]:
            for year, month in months:
                sub = "1m" if dataset == "klines" else None
                ym = f"{year:04d}-{month:02d}"
                seg = f"{dataset}/{symbol}/{sub}" if sub else f"{dataset}/{symbol}"
                fname = f"{symbol}-{sub}-{ym}.zip" if sub else f"{symbol}-{dataset}-{ym}.zip"
                url = f"https://data.binance.vision/data/futures/um/monthly/{seg}/{fname}"
                entry = manifest.get(url)
                if entry is None:
                    missing.append(url)
                elif entry["status"] == "CHECKSUM_MISMATCH":
                    checksum_failures.append(url)
                elif entry["status"] not in ("ok", "missing_404"):
                    missing.append(url)
    return {
        "n_manifest_entries": len(manifest),
        "n_expected_month_files": len(SYMBOLS) * 3 * len(months),
        "missing_or_unrecorded": missing,
        "checksum_failures": checksum_failures,
    }


def check_qa_ingest_log() -> dict:
    if not QA_LOG_PATH.exists():
        return {"n_months_logged": 0, "anomalous_months": []}
    records = [json.loads(line) for line in open(QA_LOG_PATH, encoding="utf-8") if line.strip()]
    anomalous = [r for r in records if r.get("anomalous")]
    return {"n_months_logged": len(records), "anomalous_months": anomalous}


def full_period_volume_reconciliation() -> dict:
    results = {}
    for symbol in SYMBOLS:
        bars_path = PARQUET_DIR / symbol / "bars.parquet"
        if not bars_path.exists():
            results[symbol] = {"error": "bars.parquet not found - run phase2_etl finalize first"}
            continue
        bars = pl.read_parquet(bars_path)
        agg_total = float(bars["volume"].sum())

        kl_files = sorted((STAGING_DIR / symbol).glob("*_klines.parquet"))
        kl_total = 0.0
        for f in kl_files:
            kl_total += float(pl.read_parquet(f)["volume"].sum())

        results[symbol] = qa.reconcile_volume(agg_total, kl_total)
        results[symbol]["n_kline_months"] = len(kl_files)
    return results


def write_report(manifest_check: dict, log_check: dict, recon: dict) -> None:
    lines = []
    lines.append("# Phase 2 QA Summary")
    lines.append("")
    lines.append("Runner-generated (runners/phase2_qa.py). Do not hand-edit.")
    lines.append("")
    lines.append("## Manifest completeness")
    lines.append("")
    lines.append(f"- Manifest entries: {manifest_check['n_manifest_entries']}")
    lines.append(f"- Expected monthly files (symbols x datasets x months): {manifest_check['n_expected_month_files']}")
    lines.append(f"- Missing or unrecorded: {len(manifest_check['missing_or_unrecorded'])}")
    lines.append(f"- Checksum failures: {len(manifest_check['checksum_failures'])}")
    if manifest_check["missing_or_unrecorded"]:
        lines.append("")
        lines.append("Missing URLs:")
        for u in manifest_check["missing_or_unrecorded"]:
            lines.append(f"- {u}")
    if manifest_check["checksum_failures"]:
        lines.append("")
        lines.append("Checksum failure URLs:")
        for u in manifest_check["checksum_failures"]:
            lines.append(f"- {u}")
    lines.append("")
    lines.append("## Inline gap / monotonicity scan (per ingested month)")
    lines.append("")
    lines.append(f"- Months logged: {log_check['n_months_logged']}")
    lines.append(f"- Anomalous months: {len(log_check['anomalous_months'])}")
    for r in log_check["anomalous_months"]:
        lines.append(
            f"  - {r['symbol']} {r['year']:04d}-{r['month']:02d}: "
            f"monotonic={r['raw_order_monotonic']}, missing_days={r['missing_days']}, "
            f"agg_id_gaps={r['n_agg_id_gaps']}"
        )
    lines.append("")
    lines.append("## Full-period aggTrades vs klines volume reconciliation (gate: <0.5%)")
    lines.append("")
    for symbol, r in recon.items():
        if "error" in r:
            lines.append(f"- {symbol}: ERROR - {r['error']}")
            continue
        status = "PASS" if r["within_tolerance"] else "FAIL"
        lines.append(
            f"- {symbol}: aggTrades={r['agg_trades_volume']:,.2f}, klines={r['klines_volume']:,.2f} "
            f"({r['n_kline_months']} months), diff={r['diff_pct']:.4f}% -> {status}"
        )
    lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


def run() -> bool:
    manifest_check = check_manifest_completeness()
    log_check = check_qa_ingest_log()
    recon = full_period_volume_reconciliation()
    write_report(manifest_check, log_check, recon)

    all_ok = (
        len(manifest_check["checksum_failures"]) == 0
        and all(r.get("within_tolerance", False) for r in recon.values() if "error" not in r)
    )
    print("QA gate:", "PASS" if all_ok else "FAIL (see reports/QA_SUMMARY.md)")
    return all_ok


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
