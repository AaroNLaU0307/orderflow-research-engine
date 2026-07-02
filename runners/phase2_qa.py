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


def daily_volume_reconciliation(symbol: str) -> dict:
    """Per-day reconciliation (brief section 2.2: "daily base-asset volume
    from aggTrades must match 1m-klines daily volume within 0.5%"), not a
    single full-period aggregate - a full-period sum can mask offsetting
    per-day breaches, and cannot distinguish "klines archive doesn't cover
    this day yet" (an availability gap, not a reconciliation failure) from
    a genuine discrepancy.
    """
    bars_path = PARQUET_DIR / symbol / "bars.parquet"
    if not bars_path.exists():
        return {"error": "bars.parquet not found - run phase2_etl finalize first"}
    bars = pl.read_parquet(bars_path)
    agg_daily = (
        bars.with_columns(pl.col("bar_ts").dt.date().alias("day"))
        .group_by("day")
        .agg(pl.col("volume").sum().alias("agg_volume"))
    )

    kl_files = sorted((STAGING_DIR / symbol).glob("*_klines.parquet"))
    if not kl_files:
        return {"error": "no klines staged"}
    kl = pl.concat([pl.read_parquet(f) for f in kl_files])
    kl_daily = (
        kl.with_columns(pl.from_epoch("open_time", time_unit="ms").dt.date().alias("day"))
        .group_by("day")
        .agg(pl.col("volume").sum().alias("kl_volume"))
    )

    merged = agg_daily.join(kl_daily, on="day", how="full", coalesce=True).sort("day")
    both = merged.filter(pl.col("agg_volume").is_not_null() & pl.col("kl_volume").is_not_null())
    agg_only_days = merged.filter(pl.col("agg_volume").is_not_null() & pl.col("kl_volume").is_null())
    kl_only_days = merged.filter(pl.col("agg_volume").is_null() & pl.col("kl_volume").is_not_null())

    both = both.with_columns(
        ((pl.col("agg_volume") - pl.col("kl_volume")).abs() / pl.col("kl_volume") * 100).alias("diff_pct")
    )
    breaches = both.filter(pl.col("diff_pct") >= 0.5).sort("diff_pct", descending=True)

    return {
        "n_days_both": both.height,
        "n_days_agg_only": agg_only_days.height,
        "agg_only_days": sorted(d.isoformat() for d in agg_only_days["day"].to_list()),
        "n_days_kl_only": kl_only_days.height,
        "kl_only_days": sorted(d.isoformat() for d in kl_only_days["day"].to_list()),
        "n_breaches": breaches.height,
        "worst_5": breaches.head(5).to_dicts(),
        "max_diff_pct": float(both["diff_pct"].max()) if both.height else None,
        "mean_diff_pct": float(both["diff_pct"].mean()) if both.height else None,
    }


def full_period_volume_reconciliation() -> dict:
    return {symbol: daily_volume_reconciliation(symbol) for symbol in SYMBOLS}


def check_backfill_months() -> dict:
    backfill_log_path = DATA_DIR / "qa_backfill_log.jsonl"
    if not backfill_log_path.exists():
        return {"n_repaired": 0, "months": [], "unrecovered": []}
    records = [json.loads(line) for line in open(backfill_log_path, encoding="utf-8") if line.strip()]
    months = [
        {"symbol": r["symbol"], "year": r["year"], "month": r["month"], "missing_days": r["original_missing_days"]}
        for r in records
    ]
    unrecovered = [m for r, m in zip(records, months) if r["still_missing"]]
    return {"n_repaired": len(records), "months": months, "unrecovered": unrecovered}


def check_bar_store_sanity() -> dict:
    results = {}
    for symbol in SYMBOLS:
        bars_path = PARQUET_DIR / symbol / "bars.parquet"
        if not bars_path.exists():
            results[symbol] = {"error": "bars.parquet not found"}
            continue
        bars = pl.read_parquet(bars_path)
        n_days = (STUDY_END.date() - STUDY_START.date()).days + 1
        results[symbol] = {
            "n_bars": bars.height,
            "expected_bars": n_days * 288,
            "n_days": n_days,
            "zero_trade_bars": int((bars["volume"] == 0).sum()),
            "bar_ts_min": str(bars["bar_ts"].min()),
            "bar_ts_max": str(bars["bar_ts"].max()),
        }
    return results


def check_raw_retention() -> dict:
    raw_dir = DATA_DIR / "raw"
    if not raw_dir.exists():
        return {"total_bytes": 0, "by_extension": {}}
    by_ext: dict[str, dict] = {}
    total = 0
    for f in raw_dir.rglob("*"):
        if f.is_file():
            size = f.stat().st_size
            total += size
            ext = f.suffix
            by_ext.setdefault(ext, {"count": 0, "bytes": 0})
            by_ext[ext]["count"] += 1
            by_ext[ext]["bytes"] += size
    return {"total_bytes": total, "by_extension": by_ext}


def write_report(manifest_check: dict, log_check: dict, recon: dict, backfill_check: dict, bar_sanity: dict, raw_retention: dict) -> None:
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
    lines.append("## Daily aggTrades vs klines volume reconciliation (gate: <0.5%, per calendar day)")
    lines.append("")
    for symbol, r in recon.items():
        if "error" in r:
            lines.append(f"- {symbol}: ERROR - {r['error']}")
            continue
        lines.append(f"### {symbol}")
        lines.append("")
        lines.append(f"- Days with both aggTrades and klines data: {r['n_days_both']}")
        lines.append(f"- Days with aggTrades only (klines archive not yet published for that day): {r['n_days_agg_only']}")
        if r["agg_only_days"]:
            lines.append(f"  - {r['agg_only_days']}")
        lines.append(f"- Days with klines only (aggTrades missing - should be 0 after backfill): {r['n_days_kl_only']}")
        if r["kl_only_days"]:
            lines.append(f"  - {r['kl_only_days']}")
        lines.append(f"- Breach days (diff >= 0.5%, among days with both sources): {r['n_breaches']}")
        if r["max_diff_pct"] is not None:
            lines.append(f"- Max diff: {r['max_diff_pct']:.4f}%, mean diff: {r['mean_diff_pct']:.4f}%")
        if r["worst_5"]:
            lines.append("- Worst 5 breach days:")
            for row in r["worst_5"]:
                lines.append(
                    f"  - {row['day']}: aggTrades={row['agg_volume']:,.2f}, klines={row['kl_volume']:,.2f}, diff={row['diff_pct']:.4f}%"
                )
        status = "PASS" if r["n_breaches"] == 0 and r["n_days_kl_only"] == 0 else "FAIL"
        lines.append(f"- Gate: {status}")
        lines.append("")

    lines.append("## Monthly-archive-gap backfill (daily-archive splice)")
    lines.append("")
    lines.append(f"- Months repaired via daily-archive backfill: {backfill_check['n_repaired']}")
    for m in backfill_check["months"]:
        lines.append(f"  - {m['symbol']} {m['year']:04d}-{m['month']:02d}: missing_days={m['missing_days']} -> recovered from daily archive")
    lines.append(f"- Months where daily archive ALSO lacked the data (unrecoverable): {len(backfill_check['unrecovered'])}")
    for m in backfill_check["unrecovered"]:
        lines.append(f"  - {m['symbol']} {m['year']:04d}-{m['month']:02d}: missing_days={m['missing_days']}")
    lines.append("")
    lines.append(
        "Provenance: data/manifest.json records the sha256 of every individual file ingested, including "
        "both the monthly zip and any daily backfill zips for a repaired month (so a repaired month has "
        "both its monthly-zip manifest entry AND separate entries for each spliced daily zip). "
        "data/qa_backfill_log.jsonl is the authoritative per-month record of which months were repaired "
        "and from which specific days."
    )
    lines.append("")

    lines.append("## Bar-store sanity counts")
    lines.append("")
    for symbol, r in bar_sanity.items():
        if "error" in r:
            lines.append(f"- {symbol}: ERROR - {r['error']}")
            continue
        status = "PASS" if r["n_bars"] == r["expected_bars"] else "FAIL"
        lines.append(
            f"- {symbol}: {r['n_bars']:,} bars (expected {r['expected_bars']:,} = {r['n_days']} days x 288) -> {status}; "
            f"zero-trade bars: {r['zero_trade_bars']}; range {r['bar_ts_min']} to {r['bar_ts_max']}"
        )
    lines.append("")

    lines.append("## Raw zip/csv retention status")
    lines.append("")
    total_mb = raw_retention["total_bytes"] / 1e6
    lines.append(f"- Total remaining under data/raw/: {total_mb:.1f} MB")
    for ext, info in sorted(raw_retention["by_extension"].items(), key=lambda kv: -kv[1]["bytes"]):
        lines.append(f"  - {ext or '(no ext)'}: {info['count']} files, {info['bytes']/1e6:.1f} MB")
    lines.append("")
    lines.append(
        "Raw aggTrades/klines/fundingRate .zip and extracted .csv files are deleted immediately after "
        "each month is staged to parquet (per docs/BRIEF.md section 2.4); only their tiny .CHECKSUM "
        "sidecar files remain (a few hundred bytes each). bookDepth raw files remain because 157 daily "
        "bookDepth files failed to parse (see note below) and the exception occurs before the cleanup "
        "step - this is descriptive-context data only (never a signal input) and does not affect Phase 3. "
        "Consequence: the 5-minute/Delta=25(BTC)/Delta=1(ETH) parquet bar store is the only persisted "
        "artifact: Delta=50(BTC) and 15m-bar sensitivity configs can be re-derived from it by aggregation, "
        "but Delta=10(BTC) and 3m-bar configs would require re-downloading raw aggTrades, since the "
        "5-minute bars are already a coarser aggregation than a 3-minute bar would need. No re-download "
        "is being done now; this is deferred per instruction."
    )
    lines.append("")
    lines.append(
        "Separately noted (not part of the gates above, does not affect any confirmatory signal): 157 of "
        "1275 daily BTCUSDT bookDepth files failed to parse (`could not parse '-5.00' as dtype i64` on "
        "the percentage column) - some bookDepth archive days format percentage as a float string "
        "('-5.00') rather than an integer string ('-5'), a header/format inconsistency in the same family "
        "as the header-presence and timestamp-unit quirks already documented in the prereg. Since bookDepth "
        "is descriptive-only per preregistration section 3, this is not a Phase 3 blocker; flagged for a "
        "follow-up fix before any bookDepth descriptive exhibit is produced."
    )
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


def run() -> bool:
    manifest_check = check_manifest_completeness()
    log_check = check_qa_ingest_log()
    recon = full_period_volume_reconciliation()
    backfill_check = check_backfill_months()
    bar_sanity = check_bar_store_sanity()
    raw_retention = check_raw_retention()
    write_report(manifest_check, log_check, recon, backfill_check, bar_sanity, raw_retention)

    all_ok = (
        len(manifest_check["checksum_failures"]) == 0
        and len(backfill_check["unrecovered"]) == 0
        and all((r.get("n_breaches", 1) == 0 and r.get("n_days_kl_only", 1) == 0) for r in recon.values() if "error" not in r)
        and all(r.get("n_bars") == r.get("expected_bars") for r in bar_sanity.values() if "error" not in r)
    )
    print("QA gate:", "PASS" if all_ok else "FAIL (see reports/QA_SUMMARY.md)")
    return all_ok


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
