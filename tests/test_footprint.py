import datetime as dt

import polars as pl

from orderflow import footprint

UTC = dt.timezone.utc


def _trade(agg_id, price, qty, ts_ms, is_buyer_maker):
    return dict(
        agg_trade_id=agg_id,
        price=price,
        quantity=qty,
        first_trade_id=agg_id,
        last_trade_id=agg_id,
        transact_time=ts_ms,
        is_buyer_maker=is_buyer_maker,
    )


def test_aggregate_month_basic_ohlc_and_delta():
    bar0 = 1_700_000_000_000  # arbitrary 5-min-aligned ms epoch (assumed aligned for this test)
    bar0 = (bar0 // (5 * 60_000)) * (5 * 60_000)
    trades = pl.DataFrame(
        [
            _trade(1, 100.0, 1.0, bar0 + 0, False),  # buy
            _trade(2, 101.0, 2.0, bar0 + 1000, True),  # sell
            _trade(3, 99.0, 0.5, bar0 + 2000, True),  # sell
            _trade(4, 100.5, 1.5, bar0 + 3000, False),  # buy
        ]
    ).with_columns(
        [
            pl.col("price").cast(pl.Float64),
            pl.col("quantity").cast(pl.Float64),
            pl.col("transact_time").cast(pl.Int64),
            pl.col("is_buyer_maker").cast(pl.Boolean),
        ]
    )
    bars, buckets = footprint.aggregate_month(trades, delta=1.0)
    assert bars.height == 1
    row = bars.row(0, named=True)
    assert row["open"] == 100.0
    assert row["high"] == 101.0
    assert row["low"] == 99.0
    assert row["close"] == 100.5
    assert row["volume"] == 5.0
    # buy_vol = 1.0 + 1.5 = 2.5, sell_vol = 2.0 + 0.5 = 2.5 -> delta = 0
    assert row["delta"] == 0.0
    assert buckets["buy_vol"].sum() + buckets["sell_vol"].sum() == 5.0


def test_finalize_forward_fills_zero_trade_bars():
    bar_ms = 5 * 60_000
    start = dt.datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = dt.datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC)  # 3 bars: :00, :05, :10
    start_ms = int(start.timestamp() * 1000)

    # trades only in bar 0 (:00) and bar 2 (:10); bar 1 (:05) has none
    trades = pl.DataFrame(
        [
            _trade(1, 100.0, 1.0, start_ms, False),
            _trade(2, 105.0, 1.0, start_ms + 2 * bar_ms, True),
        ]
    ).with_columns(
        [
            pl.col("price").cast(pl.Float64),
            pl.col("quantity").cast(pl.Float64),
            pl.col("transact_time").cast(pl.Int64),
            pl.col("is_buyer_maker").cast(pl.Boolean),
        ]
    )
    partial_bars, partial_buckets = footprint.aggregate_month(trades, delta=25.0)
    bars = footprint.finalize_symbol_bars(partial_bars, start, end)
    assert bars.height == 3

    b0, b1, b2 = bars.sort("bar_index").iter_rows(named=True)
    assert b0["volume"] == 1.0
    assert b1["volume"] == 0.0
    assert b1["open"] == b1["high"] == b1["low"] == b1["close"] == b0["close"]
    assert b1["delta"] == 0.0
    assert b2["volume"] == 1.0
    assert b2["open"] == 105.0

    # cumulative_delta is a running sum across the whole continuous grid
    assert bars.sort("bar_index")["cumulative_delta"].to_list() == [
        b0["delta"],
        b0["delta"] + b1["delta"],
        b0["delta"] + b1["delta"] + b2["delta"],
    ]

    buckets = footprint.finalize_symbol_buckets(partial_buckets, bars)
    # bar 1 (zero trades) must contribute no bucket rows at all
    assert buckets.filter(pl.col("bar_index") == 1).height == 0
