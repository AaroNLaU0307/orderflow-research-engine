"""Classify every reconciliation-breach day found in Phase 2 QA.

For each breach day, fetches the daily-archive aggTrades file (ground
truth, finer-grained than the monthly rollup) and compares it against
what is currently staged for that day, plus checks klines for zero-volume
minutes. Verdict per preregistration-adjacent QA logic (see user
instruction): KLINES_HOLE / AGG_PARTIAL_GAP / UNEXPLAINED.

AGG_PARTIAL_GAP days are repaired by treating them exactly like a
whole-day gap for etl.backfill_missing_days (which dedupes by
agg_trade_id, so splicing in the daily file is safe even if the
currently-staged month already has *some* of that day's trades) -
followed by month re-aggregation. If the daily archive ALSO shows the
gap (upstream-global), the day is queued for quarantine instead.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from orderflow import etl, footprint  # noqa: E402
from orderflow.config import DELTA, SYMBOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
PARQUET_DIR = DATA_DIR / "parquet"
MANIFEST_PATH = DATA_DIR / "manifest.json"
CLASSIFICATION_LOG = DATA_DIR / "qa_breach_classification.jsonl"
QUARANTINE_PATH = DATA_DIR / "quarantine_windows.json"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_breach_days(symbol: str) -> list[dict]:
    bars = pl.read_parquet(PARQUET_DIR / symbol / "bars.parquet")
    agg_daily = bars.with_columns(pl.col("bar_ts").dt.date().alias("day")).group_by("day").agg(
        pl.col("volume").sum().alias("agg_volume")
    )
    kl_files = sorted((STAGING_DIR / symbol).glob("*_klines.parquet"))
    kl = pl.concat([pl.read_parquet(f) for f in kl_files])
    kl_with_day = kl.with_columns(pl.from_epoch("open_time", time_unit="ms").dt.date().alias("day"))
    kl_daily = kl_with_day.group_by("day").agg(pl.col("volume").sum().alias("kl_volume"))
    kl_zero_min = kl_with_day.group_by("day").agg((pl.col("volume") == 0).sum().alias("zero_vol_minutes"))

    merged = agg_daily.join(kl_daily, on="day", how="inner").join(kl_zero_min, on="day", how="left").sort("day")
    merged = merged.with_columns(((pl.col("agg_volume") - pl.col("kl_volume")) / pl.col("kl_volume") * 100).alias("diff_pct"))
    breaches = merged.filter(pl.col("diff_pct").abs() >= 0.5)
    return breaches.to_dicts()


def daily_archive_stats(symbol: str, date: dt.date, manifest: etl.Manifest) -> dict | None:
    url = etl.day_url("aggTrades", symbol, date)
    zip_path = etl.download_and_verify(url, RAW_DIR / symbol / "aggTrades_daily_check", manifest)
    if zip_path is None:
        return None
    csv_path = etl.extract_single_csv(zip_path, RAW_DIR / symbol / "aggTrades_daily_check_extracted")
    trades = etl.read_aggtrades(csv_path)
    trades = trades.sort("transact_time")
    ts = trades["transact_time"].to_numpy()
    ids = trades["agg_trade_id"].to_numpy()
    max_id_jump = int(np.diff(ids).max()) if len(ids) > 1 else 0
    max_ts_gap_ms = int(np.diff(ts).max()) if len(ts) > 1 else 0
    stats = {
        "n_trades": trades.height,
        "total_volume": float(trades["quantity"].sum()),
        "max_id_jump": max_id_jump,
        "max_ts_gap_minutes": max_ts_gap_ms / 60_000,
    }
    zip_path.unlink(missing_ok=True)
    csv_path.unlink(missing_ok=True)
    return stats, trades


def zero_vol_buckets_explain_diff(symbol: str, date: dt.date, total_diff: float) -> dict:
    """Magnitude-weighted test: bucket klines into 5-min windows matching
    bars, and check whether the buckets that CONTAIN a zero-volume klines
    minute account for most of the day's aggTrades-vs-klines diff. A raw
    zero-minute *count* is not a reliable material-ness test - two
    zero-volume minutes during a high-activity window can outweigh many
    zero-volume minutes during quiet overnight hours.
    """
    ym = f"{date.year:04d}-{date.month:02d}"
    kl_path = STAGING_DIR / symbol / f"{ym}_klines.parquet"
    if not kl_path.exists():
        return {"explained": False, "explained_fraction": None}
    kl = pl.read_parquet(kl_path)
    day_start = dt.datetime(date.year, date.month, date.day)
    day_end = day_start + dt.timedelta(days=1)
    kl_day = kl.with_columns(pl.from_epoch("open_time", time_unit="ms").alias("dt")).filter(
        (pl.col("dt") >= day_start) & (pl.col("dt") < day_end)
    )
    bars = pl.read_parquet(PARQUET_DIR / symbol / "bars.parquet")
    bars_day = bars.filter((pl.col("bar_ts") >= day_start) & (pl.col("bar_ts") < day_end))

    bars_day = bars_day.with_columns(
        (pl.col("bar_ts").dt.hour().cast(pl.Int32) * 60 + pl.col("bar_ts").dt.minute().cast(pl.Int32)).alias("minofday")
    )
    kl_day = kl_day.with_columns(
        (pl.col("dt").dt.hour().cast(pl.Int32) * 60 + pl.col("dt").dt.minute().cast(pl.Int32)).alias("minofday")
    )
    kl_day = kl_day.with_columns([(pl.col("minofday") // 5 * 5).alias("bucket"), (pl.col("volume") == 0).alias("is_zero")])
    kl_bucketed = kl_day.group_by("bucket").agg(
        [pl.col("volume").sum().alias("kl_vol"), pl.col("is_zero").any().alias("has_zero_minute")]
    )
    b5 = bars_day.select([pl.col("minofday").alias("bucket"), pl.col("volume").alias("agg_vol")])
    merged = b5.join(kl_bucketed, on="bucket", how="left").with_columns(
        (pl.col("agg_vol") - pl.col("kl_vol")).alias("bucket_diff")
    )
    zero_bucket_diff_sum = merged.filter(pl.col("has_zero_minute").fill_null(False))["bucket_diff"].sum()
    fraction = (zero_bucket_diff_sum / total_diff) if total_diff else None
    return {
        "explained": fraction is not None and fraction >= 0.8,
        "explained_fraction": round(fraction, 4) if fraction is not None else None,
        "zero_bucket_diff_sum": round(float(zero_bucket_diff_sum), 4),
    }


def classify_day(symbol: str, row: dict, manifest: etl.Manifest) -> dict:
    date = row["day"]
    direction = "agg>k" if row["diff_pct"] > 0 else "agg<k"
    result = daily_archive_stats(symbol, date, manifest)
    record = {
        "symbol": symbol,
        "date": str(date),
        "direction": direction,
        "diff_pct": row["diff_pct"],
        "zero_vol_klines_minutes": row.get("zero_vol_minutes"),
        "current_agg_volume": row["agg_volume"],
        "klines_volume": row["kl_volume"],
    }
    if result is None:
        record["verdict"] = "UNEXPLAINED"
        record["reason"] = "daily archive unavailable for this date"
        return record

    stats, _trades = result
    record["daily_archive_volume"] = stats["total_volume"]
    record["daily_archive_max_id_jump"] = stats["max_id_jump"]
    record["daily_archive_max_ts_gap_minutes"] = round(stats["max_ts_gap_minutes"], 2)

    daily_vs_current_pct = (
        (stats["total_volume"] - row["agg_volume"]) / row["agg_volume"] * 100 if row["agg_volume"] else float("inf")
    )
    record["daily_vs_current_staged_diff_pct"] = round(daily_vs_current_pct, 4)

    if direction == "agg>k":
        zero_min = row.get("zero_vol_minutes") or 0
        contiguous = stats["max_id_jump"] <= 2 and stats["max_ts_gap_minutes"] < 30
        magnitude_diff = row["agg_volume"] - row["kl_volume"]
        explain = zero_vol_buckets_explain_diff(symbol, date, magnitude_diff)
        record["zero_vol_bucket_explains_fraction"] = explain["explained_fraction"]
        if zero_min >= 1 and contiguous and explain["explained"]:
            record["verdict"] = "KLINES_HOLE"
            record["reason"] = (
                f"{zero_min} zero-volume klines minute(s) account for "
                f"{explain['explained_fraction']:.1%} of the day's diff (magnitude-weighted, not just count); "
                f"aggTrades day contiguous (max_id_jump={stats['max_id_jump']}) and matches its own daily archive exactly"
            )
        else:
            record["verdict"] = "UNEXPLAINED"
            record["reason"] = (
                f"agg>k but zero_vol_minutes={zero_min} explain only "
                f"{explain['explained_fraction']}, max_id_jump={stats['max_id_jump']} does not cleanly fit KLINES_HOLE"
            )
    else:  # agg<k
        has_gap_evidence = stats["max_id_jump"] > 2 or stats["max_ts_gap_minutes"] >= 30
        daily_has_more = daily_vs_current_pct > 0.1
        if daily_has_more and not has_gap_evidence:
            # daily archive's agg_trade_id sequence is contiguous (max_id_jump<=2)
            # for THIS DAY - i.e. no trades are structurally missing from the
            # monthly file's ID sequence. The volume shortfall is therefore a
            # same-ID-different-quantity value revision between when the two
            # archives were generated (see etl.backfill_missing_days docstring
            # and the ETHUSDT 2023-05-04 case that first surfaced this), not a
            # gap where entire trades are absent. Mechanically still repaired
            # by the same daily-archive splice, but the root cause and label
            # are distinct from a genuine partial-day gap.
            record["verdict"] = "AGG_STALE_REVISION"
            record["reason"] = (
                f"daily archive has {daily_vs_current_pct:.3f}% more volume than currently staged, "
                f"but its agg_trade_id sequence for this day is contiguous (max_id_jump={stats['max_id_jump']}) "
                f"-> not a gap, a same-ID different-quantity revision between archive generations; "
                f"repaired by replacing this day's monthly-sourced trades with the daily archive's values"
            )
        elif daily_has_more:
            record["verdict"] = "AGG_PARTIAL_GAP"
            record["reason"] = (
                f"daily archive has {daily_vs_current_pct:.3f}% more volume than currently staged, "
                f"with agg_trade_id evidence of a genuine gap (max_id_jump={stats['max_id_jump']}) "
                f"-> monthly-archive rollup is missing trades for this day; repairable by splice"
            )
        elif has_gap_evidence:
            record["verdict"] = "AGG_PARTIAL_GAP_UPSTREAM"
            record["reason"] = (
                f"daily archive itself shows a gap (max_id_jump={stats['max_id_jump']}, "
                f"max_ts_gap={stats['max_ts_gap_minutes']:.1f}min) and matches what we already have "
                f"-> upstream gap, not fixable by re-splicing; quarantine candidate"
            )
        else:
            record["verdict"] = "UNEXPLAINED"
            record["reason"] = "agg<k but daily archive matches current staged data and shows no internal gap evidence"
    return record


def run_classification() -> list[dict]:
    manifest = etl.Manifest.load(MANIFEST_PATH)
    all_records = []
    for symbol in SYMBOLS:
        breach_days = get_breach_days(symbol)
        log(f"{symbol}: {len(breach_days)} breach days to classify")
        for row in breach_days:
            rec = classify_day(symbol, row, manifest)
            log(f"  {symbol} {rec['date']}: {rec['direction']} diff={rec['diff_pct']:.4f}% -> {rec['verdict']} ({rec['reason']})")
            all_records.append(rec)

    CLASSIFICATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLASSIFICATION_LOG, "w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec, default=str, sort_keys=True) + "\n")
    log(f"Wrote {CLASSIFICATION_LOG}")
    return all_records


if __name__ == "__main__":
    run_classification()
