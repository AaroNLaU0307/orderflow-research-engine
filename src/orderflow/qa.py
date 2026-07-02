"""QA checks that must run on raw ticks before they are discarded (per
docs/BRIEF.md section 2.2: gap scan, intraday monotonicity) plus the
post-ingest reconciliation check (aggTrades volume vs klines volume, within
0.5%). Findings are logged, never silently dropped - see
runners/phase2_etl.py's use of `log_qa_finding` and runners/phase2_qa.py for
the full-period reconciliation pass.
"""
from __future__ import annotations

import calendar
import json
from pathlib import Path

import polars as pl


def check_raw_trade_order(trades: pl.DataFrame) -> dict:
    """Monotonicity of transact_time in the file AS READ, before any
    defensive re-sort in aggregate_month. A violation here means the
    upstream Binance archive file itself was not time-ordered."""
    ts = trades["transact_time"]
    diffs = ts.diff().drop_nulls()
    n_out_of_order = int((diffs < 0).sum())
    agg_ids = trades["agg_trade_id"]
    id_diffs = agg_ids.diff().drop_nulls()
    n_id_gaps = int((id_diffs != 1).sum())
    return {
        "n_trades": trades.height,
        "raw_order_monotonic": n_out_of_order == 0,
        "n_out_of_order_pairs": n_out_of_order,
        "n_agg_id_gaps": n_id_gaps,
    }


def check_daily_coverage(trades: pl.DataFrame, year: int, month: int) -> dict:
    """Which calendar days within this month have zero trades at all (a
    full missing day - distinct from an individual zero-trade 5-min bar,
    which finalize_symbol_bars already handles via forward-fill)."""
    days_in_month = calendar.monthrange(year, month)[1]
    day_col = pl.from_epoch(trades["transact_time"], time_unit="ms").dt.day()
    counts = trades.with_columns(day_col.alias("day")).group_by("day").len()
    present_days = set(counts["day"].to_list())
    all_days = set(range(1, days_in_month + 1))
    missing_days = sorted(all_days - present_days)
    return {"days_in_month": days_in_month, "missing_days": missing_days, "n_days_present": len(present_days)}


def append_qa_log(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def log_month_qa(log_path: Path, symbol: str, year: int, month: int, trades: pl.DataFrame) -> dict:
    order = check_raw_trade_order(trades)
    coverage = check_daily_coverage(trades, year, month)
    record = {
        "symbol": symbol,
        "year": year,
        "month": month,
        **order,
        **coverage,
    }
    anomalous = (not order["raw_order_monotonic"]) or (len(coverage["missing_days"]) > 0)
    record["anomalous"] = anomalous
    append_qa_log(log_path, record)
    return record


def reconcile_volume(agg_trades_volume: float, klines_volume: float) -> dict:
    diff_pct = abs(agg_trades_volume - klines_volume) / klines_volume * 100 if klines_volume else float("inf")
    return {
        "agg_trades_volume": agg_trades_volume,
        "klines_volume": klines_volume,
        "diff_pct": diff_pct,
        "within_tolerance": diff_pct < 0.5,
    }
