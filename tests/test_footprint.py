import datetime as dt

import polars as pl
import pytest

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


def _build_multi_bar_store(n_5min_bars: int, seed: int = 0):
    """A gap-free, real-pipeline-built 5-min/Delta=25 store spanning
    n_5min_bars bars, for exercising rebucket/rebar (section 8 sensitivity
    grid derivation)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    bar_ms = 5 * 60_000
    start = dt.datetime(2024, 1, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1000)
    end = start + dt.timedelta(minutes=5 * (n_5min_bars - 1))

    trades = []
    agg_id = 1
    base_price = 50_000.0
    for i in range(n_5min_bars):
        n_trades = rng.integers(5, 15)
        bar_start_ms = start_ms + i * bar_ms
        for _ in range(n_trades):
            price = base_price + rng.integers(-100, 100)  # spans multiple $25 buckets
            qty = float(rng.uniform(0.1, 2.0))
            ts = bar_start_ms + int(rng.integers(0, bar_ms - 1))
            is_maker = bool(rng.integers(0, 2))
            trades.append(_trade(agg_id, price, qty, ts, is_maker))
            agg_id += 1

    trades_df = pl.DataFrame(trades).with_columns(
        [
            pl.col("price").cast(pl.Float64),
            pl.col("quantity").cast(pl.Float64),
            pl.col("transact_time").cast(pl.Int64),
            pl.col("is_buyer_maker").cast(pl.Boolean),
        ]
    )
    partial_bars, partial_buckets = footprint.aggregate_month(trades_df, delta=25.0)
    bars = footprint.finalize_symbol_bars(partial_bars, start, end)
    buckets = footprint.finalize_symbol_buckets(partial_buckets, bars)
    return bars, buckets


def test_rebucket_conserves_total_volume_and_rejects_non_multiple():
    bars, buckets = _build_multi_bar_store(12)
    rebucketed = footprint.rebucket(buckets, new_delta=50.0, old_delta=25.0)

    orig_total = (buckets["buy_vol"] + buckets["sell_vol"]).sum()
    new_total = (rebucketed["buy_vol"] + rebucketed["sell_vol"]).sum()
    assert new_total == pytest.approx(orig_total)

    # every new bucket_px must be a multiple of 50
    assert all(px % 50.0 == 0 for px in rebucketed["bucket_px"].to_list())

    with pytest.raises(ValueError):
        footprint.rebucket(buckets, new_delta=30.0, old_delta=25.0)  # not an integer multiple


def test_rebucket_merges_adjacent_pairs_correctly():
    """A known pair of adjacent Delta=25 buckets (e.g. 50000 and 50025) must
    merge into exactly one Delta=50 bucket (50000) with summed volumes."""
    buckets = pl.DataFrame(
        {
            "bar_index": [0, 0, 0],
            "bar_ts": [dt.datetime(2024, 1, 1, tzinfo=UTC)] * 3,
            "bar_ts_ms": [1704067200000] * 3,
            "bucket_px": [50000.0, 50025.0, 50050.0],
            "buy_vol": [10.0, 20.0, 5.0],
            "sell_vol": [1.0, 2.0, 3.0],
            "trade_count": [5, 6, 2],
        }
    )
    out = footprint.rebucket(buckets, new_delta=50.0, old_delta=25.0)
    out_dict = {row["bucket_px"]: row for row in out.iter_rows(named=True)}
    assert out_dict[50000.0]["buy_vol"] == 30.0  # 10+20
    assert out_dict[50000.0]["sell_vol"] == 3.0  # 1+2
    assert out_dict[50050.0]["buy_vol"] == 5.0
    assert out_dict[50050.0]["sell_vol"] == 3.0


def test_rebar_conserves_volume_and_produces_correct_ohlc():
    bars, buckets = _build_multi_bar_store(9)  # 9 five-min bars -> 3 fifteen-min bars
    new_bars, new_buckets = footprint.rebar(bars, buckets, new_bar_ms=15 * 60_000, old_bar_ms=5 * 60_000)

    assert new_bars.height == 3
    assert new_bars["volume"].sum() == pytest.approx(bars["volume"].sum())
    assert new_bars["delta"].sum() == pytest.approx(bars["delta"].sum())

    old_sorted = bars.sort("bar_index")
    for k in range(3):
        old_group = old_sorted.slice(k * 3, 3)
        new_row = new_bars.filter(pl.col("bar_index") == k).row(0, named=True)
        assert new_row["open"] == old_group["open"][0]
        assert new_row["close"] == old_group["close"][-1]
        assert new_row["high"] == old_group["high"].max()
        assert new_row["low"] == old_group["low"].min()
        assert new_row["volume"] == pytest.approx(old_group["volume"].sum())

    # cumulative_delta recomputed at the new resolution, not just resampled
    assert new_bars["cumulative_delta"].to_list() == new_bars["delta"].cum_sum().to_list()

    # bucket volume conservation through the bar regrouping too
    assert (new_buckets["buy_vol"].sum() + new_buckets["sell_vol"].sum()) == pytest.approx(
        buckets["buy_vol"].sum() + buckets["sell_vol"].sum()
    )


def test_rebar_rejects_non_multiple():
    bars, buckets = _build_multi_bar_store(6)
    with pytest.raises(ValueError):
        footprint.rebar(bars, buckets, new_bar_ms=7 * 60_000, old_bar_ms=5 * 60_000)
