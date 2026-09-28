"""Ingestion is deterministic: the same trades in any input order give byte-identical bars.

Binance archives hold many trades that share a millisecond. Before 2026-09-28 the
ingestion sorted on transact_time only and grouped without keeping order, so which
of those trades was a bar's first or last (its open/close), and the order of the
float sums, could change between runs on the same zips
(docs/CORRECTIONS_2026-09-27.md sections 10 and 12). Synthetic trades only.
"""
import datetime as dt
import io
from pathlib import Path

import numpy as np
import polars as pl

from orderflow import etl, footprint

BAR_MS = 5 * 60_000
DAY1 = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
DAY2 = DAY1 + 24 * 60 * 60 * 1000


def _trades(first_id: int, start_ms: int, n: int, seed: int) -> pl.DataFrame:
    """n trades in clusters of 3 or more sharing a millisecond, with distinct
    prices and non-dyadic quantities so both first/last and float sums can
    depend on order."""
    rng = np.random.default_rng(seed)
    ts = start_ms + np.sort(rng.integers(0, 3 * BAR_MS // 7, size=n // 3)).repeat(3)[:n] * 7
    return pl.DataFrame(
        {
            "agg_trade_id": np.arange(first_id, first_id + n, dtype=np.int64),
            "price": 100.0 + np.round(rng.normal(0, 1, n), 2),
            "quantity": np.round(rng.uniform(0.001, 3.0, n), 3) + 0.1,
            "first_trade_id": np.arange(first_id, first_id + n, dtype=np.int64),
            "last_trade_id": np.arange(first_id, first_id + n, dtype=np.int64),
            "transact_time": ts.astype(np.int64),
            "is_buyer_maker": rng.integers(0, 2, n).astype(bool),
        }
    )


def _shuffled(df: pl.DataFrame, seed: int) -> pl.DataFrame:
    return df.sample(fraction=1.0, shuffle=True, seed=seed)


def _parquet_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def _ingest(trades: pl.DataFrame) -> tuple[bytes, bytes]:
    bars, buckets = footprint.aggregate_month(trades, delta=0.25)
    return _parquet_bytes(bars), _parquet_bytes(buckets)


def test_same_millisecond_trades_exist_in_the_fixture():
    t = _trades(1, DAY1, 3000, seed=0)
    assert t["transact_time"].n_unique() < t.height


def test_aggregate_month_is_byte_identical_across_input_orders():
    trades = _trades(1, DAY1, 3000, seed=0)
    reference = _ingest(trades)
    assert _ingest(_shuffled(trades, 1)) == reference
    assert _ingest(_shuffled(trades, 2)) == reference


def test_open_and_close_break_ties_by_agg_trade_id():
    trades = _trades(1, DAY1, 3000, seed=0)
    bars, _ = footprint.aggregate_month(_shuffled(trades, 3), delta=0.25)
    ordered = trades.with_columns((pl.col("transact_time") // BAR_MS * BAR_MS).alias("bar_ts_ms")).sort(
        ["transact_time", "agg_trade_id"]
    )
    expected = ordered.group_by("bar_ts_ms", maintain_order=True).agg(
        pl.col("price").first().alias("open"), pl.col("price").last().alias("close")
    )
    got = bars.select(["bar_ts_ms", "open", "close"])
    assert got.equals(expected)


def test_backfill_then_aggregate_is_byte_identical_across_input_orders(monkeypatch):
    """The repair path: day 1 of the monthly frame is replaced by a daily frame
    whose trades share IDs with it but carry revised quantities."""
    monthly = pl.concat([_trades(1, DAY1, 1500, seed=4), _trades(1501, DAY2, 1500, seed=5)])
    daily = _trades(1, DAY1, 1500, seed=4).with_columns(pl.col("quantity") * 1.01)

    def run(seed: int) -> tuple[bytes, bytes]:
        monkeypatch.setattr(etl, "download_and_verify", lambda *a, **k: Path("fake.zip"))
        monkeypatch.setattr(etl, "extract_single_csv", lambda *a, **k: Path("fake.csv"))
        monkeypatch.setattr(etl, "read_aggtrades", lambda path: _shuffled(daily, seed + 100))
        manifest = etl.Manifest(path=Path("unused.json"))
        combined, still_missing = etl.backfill_missing_days(
            _shuffled(monthly, seed), "BTCUSDT", 2024, 1, [1], Path("."), manifest
        )
        assert still_missing == []
        return _ingest(combined)

    assert run(1) == run(2)
