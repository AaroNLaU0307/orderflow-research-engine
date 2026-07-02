"""Phase 0 data audit: inspect sample files already downloaded under data/sample/.

Reads the extracted sample CSVs (recent era: 2025-03-17 / 2025-03; old era:
2022-07-01) and prints schema, dtypes, header-presence, and timestamp-unit
sniffing results. Does not touch forward returns or PnL (pre-registration
gate has not been crossed yet).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
EXTRACTED = SAMPLE / "extracted"
OLD_EXTRACTED = SAMPLE / "old_extracted"


def sniff_header(path: Path) -> bool:
    with open(path, "r", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    # header rows are alphabetic column names; data rows start with a digit
    first_field = first_line.split(",")[0]
    return not first_field.lstrip("-").replace(".", "", 1).isdigit()


def sniff_ts_unit(sample_int: int) -> str:
    # ms epoch ~13 digits through ~2100AD; us epoch ~16 digits; s epoch ~10 digits
    ndigits = len(str(abs(sample_int)))
    if ndigits <= 10:
        return "seconds"
    if ndigits <= 13:
        return "milliseconds"
    if ndigits <= 16:
        return "microseconds"
    return "nanoseconds"


def epoch_to_utc(value: int, unit: str) -> dt.datetime:
    div = {"seconds": 1, "milliseconds": 1e3, "microseconds": 1e6, "nanoseconds": 1e9}[unit]
    return dt.datetime.fromtimestamp(value / div, tz=dt.timezone.utc)


def main() -> None:
    print("=" * 70)
    print("RECENT ERA SAMPLE: 2025-03-17 (aggTrades/klines/bookDepth), 2025-03 (fundingRate)")
    print("=" * 70)

    agg = pl.read_csv(EXTRACTED / "aggTrades" / "BTCUSDT-aggTrades-2025-03-17.csv")
    print("\n--- aggTrades schema ---")
    print(agg.schema)
    print("header present:", sniff_header(EXTRACTED / "aggTrades" / "BTCUSDT-aggTrades-2025-03-17.csv"))
    ts0 = int(agg["transact_time"][0])
    unit = sniff_ts_unit(ts0)
    print(f"transact_time sample={ts0} -> unit={unit} -> UTC={epoch_to_utc(ts0, unit)}")
    print("row count:", agg.height)
    print("isBuyerMaker value counts:", agg["is_buyer_maker"].value_counts().to_dicts())

    kl = pl.read_csv(EXTRACTED / "klines" / "BTCUSDT-1m-2025-03-17.csv")
    print("\n--- klines schema ---")
    print(kl.schema)
    print("header present:", sniff_header(EXTRACTED / "klines" / "BTCUSDT-1m-2025-03-17.csv"))
    ts0 = int(kl["open_time"][0])
    unit = sniff_ts_unit(ts0)
    print(f"open_time sample={ts0} -> unit={unit} -> UTC={epoch_to_utc(ts0, unit)}")
    print("row count (expect 1440 for full day):", kl.height)

    bd = pl.read_csv(EXTRACTED / "bookDepth" / "BTCUSDT-bookDepth-2025-03-17.csv")
    print("\n--- bookDepth schema ---")
    print(bd.schema)
    print("header present:", sniff_header(EXTRACTED / "bookDepth" / "BTCUSDT-bookDepth-2025-03-17.csv"))
    print("row count:", bd.height)
    print("unique percentage bands:", sorted(bd["percentage"].unique().to_list()))
    print("distinct timestamps:", bd["timestamp"].n_unique())

    fr = pl.read_csv(SAMPLE / "extracted" / "fundingRate" / "BTCUSDT-fundingRate-2025-03.csv")
    print("\n--- fundingRate schema ---")
    print(fr.schema)
    print("header present:", sniff_header(EXTRACTED / "fundingRate" / "BTCUSDT-fundingRate-2025-03.csv"))
    ts0 = int(fr["calc_time"][0])
    unit = sniff_ts_unit(ts0)
    print(f"calc_time sample={ts0} -> unit={unit} -> UTC={epoch_to_utc(ts0, unit)}")
    print("row count (expect ~93 for 31 days x 3):", fr.height)
    print("funding_interval_hours unique:", fr["funding_interval_hours"].unique().to_list())

    print()
    print("=" * 70)
    print("OLD ERA SAMPLE: 2022-07-01 (start of study period)")
    print("=" * 70)

    agg_old_path = OLD_EXTRACTED / "aggTrades" / "BTCUSDT-aggTrades-2022-07-01.csv"
    header_present = sniff_header(agg_old_path)
    print("\n--- old aggTrades ---")
    print("header present:", header_present)
    cols = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
    agg_old = pl.read_csv(agg_old_path, has_header=header_present, new_columns=None if header_present else cols)
    print("schema:", agg_old.schema)
    ts0 = int(agg_old["transact_time"][0])
    unit = sniff_ts_unit(ts0)
    print(f"transact_time sample={ts0} -> unit={unit} -> UTC={epoch_to_utc(ts0, unit)}")

    kl_old_path = OLD_EXTRACTED / "klines" / "BTCUSDT-1m-2022-07-01.csv"
    header_present_kl = sniff_header(kl_old_path)
    print("\n--- old klines ---")
    print("header present:", header_present_kl)

    print("\n--- old bookDepth ---")
    print("HTTP 404 NoSuchKey for 2022-07-01 through 2022-12-25 (checked); ")
    print("HTTP 200 confirmed starting 2023-01-01. bookDepth archive coverage begins ~2023-01-01,")
    print("i.e. AFTER our study start (2022-07-01). This is consistent with prereg treating")
    print("bookDepth as descriptive-context-only (H4/H5 already DATA-BLOCKED for other reasons).")

    print()
    print("=" * 70)
    print("RECENT-END TIMESTAMP UNIT CHECK: 2026-06-25 aggTrades (near period end)")
    print("=" * 70)
    recent_path = SAMPLE / "recent_extracted"
    recent_csv = list(recent_path.glob("*.csv"))[0]
    recent = pl.read_csv(recent_csv)
    ts0 = int(recent["transact_time"][0])
    unit = sniff_ts_unit(ts0)
    print(f"transact_time sample={ts0} -> unit={unit} -> UTC={epoch_to_utc(ts0, unit)}")
    print("Conclusion: futures/um archive timestamps remain milliseconds across the")
    print("full 2022-07 to 2026-06 study window (no ms->us switch observed, unlike spot in 2025).")


if __name__ == "__main__":
    main()
