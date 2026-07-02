"""Per-signal per-calendar-half-year event count table, BTC, full deduped
sample (both IS and OOS periods) - counts only, no forward returns, no OOS
statistics of any kind (preregistration OOS reservation is untouched by
this - it is purely a count of where detected events fall in calendar
time, documenting regime skew).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import events, quarantine  # noqa: E402
from orderflow.config import DELTA  # noqa: E402
from orderflow.signals import h1, h2, h3, h6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PARQUET_DIR = ROOT / "data" / "parquet"
REPORTS_DIR = ROOT / "reports"
SYMBOL = "BTCUSDT"
SIGNALS = ["H1", "H2", "H3", "H6"]
PERIODS = ["2022H2", "2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2", "2026H1"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def half_year_label(ts: object) -> str:
    y = ts.year
    h = 1 if ts.month <= 6 else 2
    return f"{y}H{h}"


def run() -> None:
    bars = pl.read_parquet(PARQUET_DIR / SYMBOL / "bars.parquet")
    buckets = pl.read_parquet(PARQUET_DIR / SYMBOL / "buckets.parquet")
    qwindows = quarantine.load_quarantine_windows()

    parts = [
        h1.detect(bars),
        h2.detect(bars, buckets, delta=DELTA[SYMBOL]),
        h3.detect(bars, buckets, delta=DELTA[SYMBOL]),
        h6.detect(bars, buckets),
    ]
    combined = pl.concat([p for p in parts if p.height > 0])
    after_q = quarantine.filter_quarantined_events(combined, SYMBOL, 5 * 60_000, qwindows)
    final = events.hygiene(after_q)
    log(f"Total final (warmup+dedup) BTC events, full sample: {final.height:,}")

    final = final.with_columns(pl.col("bar_ts").map_elements(half_year_label, return_dtype=pl.Utf8).alias("period"))
    counts = final.group_by(["signal", "period"]).len().rename({"len": "count"})

    pivot = counts.pivot(on="period", index="signal", values="count").fill_null(0)
    for p in PERIODS:
        if p not in pivot.columns:
            pivot = pivot.with_columns(pl.lit(0).alias(p))
    pivot = pivot.select(["signal"] + PERIODS)
    pivot = pivot.sort("signal")

    pivot.write_csv(REPORTS_DIR / "event_counts_by_half_year.csv")
    log(f"Wrote {REPORTS_DIR / 'event_counts_by_half_year.csv'}")

    total_events = final.height
    calendar_days_by_period = {}  # for the "calendar share" comparison
    import datetime as dt

    period_bounds = {
        "2022H2": (dt.date(2022, 7, 1), dt.date(2022, 12, 31)),
        "2023H1": (dt.date(2023, 1, 1), dt.date(2023, 6, 30)),
        "2023H2": (dt.date(2023, 7, 1), dt.date(2023, 12, 31)),
        "2024H1": (dt.date(2024, 1, 1), dt.date(2024, 6, 30)),
        "2024H2": (dt.date(2024, 7, 1), dt.date(2024, 12, 31)),
        "2025H1": (dt.date(2025, 1, 1), dt.date(2025, 6, 30)),
        "2025H2": (dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        "2026H1": (dt.date(2026, 1, 1), dt.date(2026, 6, 30)),
    }
    total_days = sum((e - s).days + 1 for s, e in period_bounds.values())
    for p, (s, e) in period_bounds.items():
        calendar_days_by_period[p] = (e - s).days + 1

    lines = []
    lines.append("# BTC Event Counts by Calendar Half-Year")
    lines.append("")
    lines.append("Runner-generated (runners/phase3_year_table.py). Do not hand-edit.")
    lines.append("")
    lines.append(
        "Full deduped BTC sample (warm-up + dedup + quarantine filter applied; both IS and OOS periods "
        "included) - counts only. No forward returns computed for OOS events; this table does not "
        "touch the OOS-reservation rule, it only documents where detected events fall in calendar time."
    )
    lines.append("")
    header = "| Signal | " + " | ".join(PERIODS) + " | Total | IS share |"
    lines.append(header)
    lines.append("|" + "---|" * (len(PERIODS) + 3))
    is_periods = {"2022H2", "2023H1", "2023H2", "2024H1", "2024H2"}
    for row in pivot.iter_rows(named=True):
        sig = row["signal"]
        total = sum(row[p] for p in PERIODS)
        is_count = sum(row[p] for p in PERIODS if p in is_periods)
        is_share = is_count / total * 100 if total else 0.0
        vals = " | ".join(str(row[p]) for p in PERIODS)
        lines.append(f"| {sig} | {vals} | {total} | {is_share:.1f}% |")
    lines.append("")
    calendar_is_share = sum(calendar_days_by_period[p] for p in is_periods) / total_days * 100
    lines.append(
        f"Calendar-time IS share (2022H2-2024H2 out of the full 2022H2-2026H1 sample): {calendar_is_share:.1f}%. "
        f"Compare each signal's IS share above against this {calendar_is_share:.1f}% baseline to see regime skew - "
        f"e.g. a signal materially above baseline fires disproportionately in the discovery period, below "
        f"baseline disproportionately post-discovery."
    )
    lines.append("")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "event_counts_by_half_year.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"Wrote {REPORTS_DIR / 'event_counts_by_half_year.md'}")


if __name__ == "__main__":
    run()
