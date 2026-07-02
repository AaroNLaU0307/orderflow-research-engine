import polars as pl

from orderflow import qa


def _trades(rows):
    return pl.DataFrame(
        rows, schema=["agg_trade_id", "transact_time"], orient="row"
    ).with_columns([pl.col("agg_trade_id").cast(pl.Int64), pl.col("transact_time").cast(pl.Int64)])


def test_check_raw_trade_order_detects_out_of_order():
    day_ms = 24 * 60 * 60 * 1000
    base = 1_700_000_000_000
    ok = _trades([(1, base), (2, base + 1000), (3, base + 2000)])
    assert qa.check_raw_trade_order(ok)["raw_order_monotonic"] is True

    bad = _trades([(1, base), (2, base - 1000), (3, base + 2000)])
    result = qa.check_raw_trade_order(bad)
    assert result["raw_order_monotonic"] is False
    assert result["n_out_of_order_pairs"] == 1


def test_check_raw_trade_order_detects_id_gaps():
    base = 1_700_000_000_000
    trades = _trades([(1, base), (2, base + 1000), (5, base + 2000)])  # gap: 2 -> 5
    result = qa.check_raw_trade_order(trades)
    assert result["n_agg_id_gaps"] == 1


def test_check_daily_coverage_detects_missing_day():
    import datetime as dt

    year, month = 2024, 1  # 31 days
    day1 = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    day3 = int(dt.datetime(2024, 1, 3, tzinfo=dt.timezone.utc).timestamp() * 1000)
    # trades on day 1 and day 3 only; day 2 (and 4..31) missing
    trades = _trades([(1, day1), (2, day1 + 1000), (3, day3)])
    result = qa.check_daily_coverage(trades, year, month)
    assert result["days_in_month"] == 31
    assert 2 in result["missing_days"]
    assert 1 not in result["missing_days"]
    assert 3 not in result["missing_days"]


def test_reconcile_volume_within_and_outside_tolerance():
    ok = qa.reconcile_volume(1000.0, 1000.4)
    assert ok["within_tolerance"] is True

    bad = qa.reconcile_volume(1000.0, 990.0)
    assert bad["within_tolerance"] is False


def test_log_month_qa_writes_jsonl(tmp_path):
    base = 1_700_000_000_000
    trades = _trades([(1, base), (2, base + 1000)])
    log_path = tmp_path / "qa.jsonl"
    record = qa.log_month_qa(log_path, "BTCUSDT", 2024, 1, trades)
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1
    assert record["symbol"] == "BTCUSDT"
    assert record["anomalous"] is True  # only 2 of 31 days present -> flagged
