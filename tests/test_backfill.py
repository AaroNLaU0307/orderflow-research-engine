import datetime as dt
from pathlib import Path

import polars as pl
import pytest

from orderflow import etl


def _trades(ids_ts):
    return pl.DataFrame(
        [(i, 100.0, 1.0, i, i, ts, False) for i, ts in ids_ts],
        schema=etl.AGGTRADES_COLUMNS,
        orient="row",
    ).with_columns(
        [
            pl.col("agg_trade_id").cast(pl.Int64),
            pl.col("price").cast(pl.Float64),
            pl.col("quantity").cast(pl.Float64),
            pl.col("first_trade_id").cast(pl.Int64),
            pl.col("last_trade_id").cast(pl.Int64),
            pl.col("transact_time").cast(pl.Int64),
            pl.col("is_buyer_maker").cast(pl.Boolean),
        ]
    )


def test_backfill_merges_daily_data_and_dedupes(tmp_path, monkeypatch):
    # monthly trades cover day 1 and day 3 only (day 2 "missing")
    day1_ms = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    day3_ms = int(dt.datetime(2024, 1, 3, tzinfo=dt.timezone.utc).timestamp() * 1000)
    day2_ms = int(dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc).timestamp() * 1000)
    monthly_trades = _trades([(1, day1_ms), (2, day3_ms)])

    daily_backfill_trades = _trades([(10, day2_ms), (11, day2_ms + 1000)])

    def fake_download_and_verify(url, dest_dir, manifest):
        return Path("fake.zip")  # non-None sentinel; content doesn't matter, read is mocked below

    def fake_extract_single_csv(zip_path, extract_dir):
        return Path("fake.csv")

    def fake_read_aggtrades(path):
        return daily_backfill_trades

    monkeypatch.setattr(etl, "download_and_verify", fake_download_and_verify)
    monkeypatch.setattr(etl, "extract_single_csv", fake_extract_single_csv)
    monkeypatch.setattr(etl, "read_aggtrades", fake_read_aggtrades)

    manifest = etl.Manifest.load(tmp_path / "manifest.json")
    combined, still_missing = etl.backfill_missing_days(
        monthly_trades, "BTCUSDT", 2024, 1, [2], tmp_path, manifest
    )

    assert still_missing == []
    assert combined.height == 4  # 2 monthly + 2 backfilled, no overlap
    assert sorted(combined["agg_trade_id"].to_list()) == [1, 2, 10, 11]
    # sorted by transact_time -> day1, day2 (x2), day3
    assert combined["transact_time"].to_list() == sorted(combined["transact_time"].to_list())


def test_backfill_reports_still_missing_when_daily_archive_also_unavailable(tmp_path, monkeypatch):
    monthly_trades = _trades([(1, 1_700_000_000_000)])

    def fake_download_and_verify(url, dest_dir, manifest):
        return None  # simulates 404 on the daily endpoint too

    monkeypatch.setattr(etl, "download_and_verify", fake_download_and_verify)

    manifest = etl.Manifest.load(tmp_path / "manifest.json")
    combined, still_missing = etl.backfill_missing_days(
        monthly_trades, "BTCUSDT", 2024, 1, [15], tmp_path, manifest
    )
    assert still_missing == [15]
    assert combined.height == 1  # unchanged, nothing to add


def test_backfill_dedupes_overlapping_agg_trade_ids(tmp_path, monkeypatch):
    """If the daily file's boundary trades overlap agg_trade_ids already
    present in the monthly file (e.g. a trade right at midnight appearing in
    both), the merge must not double-count it."""
    ts = 1_700_000_000_000
    monthly_trades = _trades([(1, ts), (2, ts + 1000)])
    overlapping_daily = _trades([(2, ts + 1000), (3, ts + 2000)])  # id=2 overlaps

    monkeypatch.setattr(etl, "download_and_verify", lambda *a, **k: Path("fake.zip"))
    monkeypatch.setattr(etl, "extract_single_csv", lambda *a, **k: Path("fake.csv"))
    monkeypatch.setattr(etl, "read_aggtrades", lambda path: overlapping_daily)

    manifest = etl.Manifest.load(tmp_path / "manifest.json")
    combined, still_missing = etl.backfill_missing_days(monthly_trades, "BTCUSDT", 2024, 1, [1], tmp_path, manifest)
    assert combined.height == 3  # ids 1,2,3 - id=2 not duplicated
    assert sorted(combined["agg_trade_id"].to_list()) == [1, 2, 3]


def test_backfill_prefers_daily_quantity_over_monthly_for_same_id(tmp_path, monkeypatch):
    """Regression test: found empirically on ETHUSDT 2023-05-04, the monthly
    and daily archives can contain the SAME agg_trade_id with DIFFERENT
    quantity values (an apparent Binance data revision between when the two
    archives were generated). Deduping the concatenation by ID alone kept
    whichever copy was listed first (the monthly/stale one) - silently
    reintroducing the exact under-count the backfill exists to fix.
    backfill_missing_days must now drop the target day's monthly rows
    entirely and trust the daily archive's values for that day, not merge
    at the trade level.
    """
    day1 = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    ts_in_day1 = int(day1.timestamp() * 1000) + 3600_000  # 01:00 UTC on day 1

    # monthly has id=5 with a STALE quantity for the trade at ts_in_day1
    monthly_trades = _trades([(5, ts_in_day1)])
    monthly_trades = monthly_trades.with_columns(pl.lit(1.0).alias("quantity"))

    # daily archive has the SAME id=5 but a CORRECTED (larger) quantity
    daily_trades = _trades([(5, ts_in_day1)])
    daily_trades = daily_trades.with_columns(pl.lit(9.0).alias("quantity"))

    monkeypatch.setattr(etl, "download_and_verify", lambda *a, **k: Path("fake.zip"))
    monkeypatch.setattr(etl, "extract_single_csv", lambda *a, **k: Path("fake.csv"))
    monkeypatch.setattr(etl, "read_aggtrades", lambda path: daily_trades)

    manifest = etl.Manifest.load(tmp_path / "manifest.json")
    combined, still_missing = etl.backfill_missing_days(monthly_trades, "BTCUSDT", 2024, 1, [1], tmp_path, manifest)

    assert combined.height == 1
    assert combined["quantity"][0] == 9.0  # daily's corrected value, not monthly's stale 1.0
