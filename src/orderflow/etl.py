"""Download, checksum, and parse Binance futures/um historical archive files.

Per preregistration/PREREGISTRATION.md section 1: every zip is verified
against its .CHECKSUM before parsing; header presence and timestamp units
are sniffed per file, never assumed; every ingested file's sha256 is
recorded in data/manifest.json.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import polars as pl
import requests

BASE_URL = "https://data.binance.vision/data/futures/um"

AGGTRADES_COLUMNS = [
    "agg_trade_id",
    "price",
    "quantity",
    "first_trade_id",
    "last_trade_id",
    "transact_time",
    "is_buyer_maker",
]
KLINES_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]
FUNDINGRATE_COLUMNS = ["calc_time", "funding_interval_hours", "last_funding_rate"]
BOOKDEPTH_COLUMNS = ["timestamp", "percentage", "depth", "notional"]

Dataset = Literal["aggTrades", "klines", "fundingRate", "bookDepth"]


def sniff_header(path: Path) -> bool:
    """True if the file's first line is a header row (alphabetic first field)."""
    with open(path, "r", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    first_field = first_line.split(",")[0]
    return not first_field.lstrip("-").replace(".", "", 1).isdigit()


def sniff_ts_unit(sample_int: int) -> str:
    ndigits = len(str(abs(int(sample_int))))
    if ndigits <= 10:
        return "seconds"
    if ndigits <= 13:
        return "milliseconds"
    if ndigits <= 16:
        return "microseconds"
    return "nanoseconds"


def normalize_ms(series: pl.Series) -> pl.Series:
    """Defensively normalize a timestamp column to milliseconds, sniffing per-call.

    Confirmed milliseconds throughout the 2022-07..2026-06 futures/um archive
    (Phase 0 audit), but sniffed rather than hardcoded per the prereg's
    data-quirks handling.
    """
    sample = series.drop_nulls()[0]
    unit = sniff_ts_unit(sample)
    if unit == "milliseconds":
        return series
    if unit == "seconds":
        return series * 1_000
    if unit == "microseconds":
        return series // 1_000
    if unit == "nanoseconds":
        return series // 1_000_000
    raise ValueError(f"unrecognized timestamp unit for sample {sample}")


# --------------------------------------------------------------------------
# URL construction
# --------------------------------------------------------------------------


def month_url(dataset: Dataset, symbol: str, year: int, month: int, sub: str | None = None) -> str:
    ym = f"{year:04d}-{month:02d}"
    seg = f"{dataset}/{symbol}/{sub}" if sub else f"{dataset}/{symbol}"
    fname = f"{symbol}-{sub}-{ym}.zip" if sub else f"{symbol}-{dataset}-{ym}.zip"
    return f"{BASE_URL}/monthly/{seg}/{fname}"


def day_url(dataset: Dataset, symbol: str, date: dt.date, sub: str | None = None) -> str:
    d = date.isoformat()
    seg = f"{dataset}/{symbol}/{sub}" if sub else f"{dataset}/{symbol}"
    fname = f"{symbol}-{sub}-{d}.zip" if sub else f"{symbol}-{dataset}-{d}.zip"
    return f"{BASE_URL}/daily/{seg}/{fname}"


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


@dataclass
class Manifest:
    path: Path
    entries: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                entries = json.load(fh)
        else:
            entries = {}
        return cls(path=path, entries=entries)

    def already_ingested(self, url: str) -> bool:
        return url in self.entries

    def record(self, url: str, sha256: str, byte_size: int, status: str = "ok") -> None:
        self.entries[url] = {
            "sha256": sha256,
            "byte_size": byte_size,
            "ingested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": status,
        }
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.entries, fh, indent=2, sort_keys=True)
        tmp.replace(self.path)


# --------------------------------------------------------------------------
# Download + checksum
# --------------------------------------------------------------------------


class ChecksumMismatch(Exception):
    pass


class RemoteFileMissing(Exception):
    pass


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, retries: int = 3, timeout: int = 120) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout) as resp:
                if resp.status_code == 404:
                    raise RemoteFileMissing(url)
                resp.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
                tmp.replace(dest)
            return
        except RemoteFileMissing:
            raise
        except Exception as exc:  # noqa: BLE001 - retry any transient network error
            last_exc = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last_exc


def download_and_verify(url: str, dest_dir: Path, manifest: Manifest) -> Path | None:
    """Download `url` + its .CHECKSUM sibling, verify sha256, record in manifest.

    Returns the local zip path, or None if the remote file does not exist
    (e.g. bookDepth before 2023-01, or a month beyond the archive's frontier).
    Idempotent: if the manifest already has an `ok` entry for this URL, skips
    re-download and returns the existing local path (re-downloading if the
    local file is missing).
    """
    fname = url.rsplit("/", 1)[-1]
    dest = dest_dir / fname
    checksum_dest = dest_dir / (fname + ".CHECKSUM")

    if manifest.already_ingested(url) and manifest.entries[url]["status"] == "ok" and dest.exists():
        return dest

    try:
        _download(url, dest)
        _download(url + ".CHECKSUM", checksum_dest)
    except RemoteFileMissing:
        manifest.record(url, sha256="", byte_size=0, status="missing_404")
        return None

    expected = checksum_dest.read_text().split()[0].strip()
    actual = _sha256_of(dest)
    byte_size = dest.stat().st_size
    if expected != actual:
        manifest.record(url, sha256=actual, byte_size=byte_size, status="CHECKSUM_MISMATCH")
        raise ChecksumMismatch(f"{url}: expected {expected}, got {actual}")

    manifest.record(url, sha256=actual, byte_size=byte_size, status="ok")
    return dest


# --------------------------------------------------------------------------
# CSV readers (header-sniffing, schema-normalizing)
# --------------------------------------------------------------------------


def _read_csv_any_header(path: Path, columns: list[str], dtypes: dict) -> pl.DataFrame:
    has_header = sniff_header(path)
    if has_header:
        df = pl.read_csv(path, schema_overrides=dtypes)
        # normalize column names defensively (archive has used both
        # camelCase and snake_case headers across eras)
        rename = {c: canon for c, canon in zip(df.columns, columns)}
        df = df.rename(rename)
    else:
        df = pl.read_csv(path, has_header=False, new_columns=columns, schema_overrides=dtypes)
    return df


def read_aggtrades(path: Path) -> pl.DataFrame:
    dtypes = {
        "agg_trade_id": pl.Int64,
        "price": pl.Float64,
        "quantity": pl.Float64,
        "first_trade_id": pl.Int64,
        "last_trade_id": pl.Int64,
        "transact_time": pl.Int64,
        "is_buyer_maker": pl.Boolean,
    }
    df = _read_csv_any_header(path, AGGTRADES_COLUMNS, dtypes)
    df = df.with_columns(normalize_ms(df["transact_time"]).alias("transact_time"))
    return df


def backfill_missing_days(
    trades: pl.DataFrame,
    symbol: str,
    year: int,
    month: int,
    missing_days: list[int],
    raw_dir: Path,
    manifest: "Manifest",
) -> tuple[pl.DataFrame, list[int]]:
    """Some monthly aggTrades archives have gaps (whole-day or partial-day)
    that the daily archive does not (confirmed empirically for BTCUSDT
    2022-08, a 3-day whole-day hole, and ETHUSDT 2023-05, a partial-day
    volume shortfall on several days - Binance archive-generation quirks,
    not genuine trading gaps). For each such day, fetch the daily zip and
    REPLACE that day's monthly-sourced trades with it entirely.

    Replace, not merge-and-dedup-by-ID: cross-checking against the daily
    archive (BTCUSDT 2022-08) found that for at least one partial-gap day
    (ETHUSDT 2023-05-04) the monthly and daily archives contain the SAME
    agg_trade_ids but DIFFERENT quantity values (782,735 trades in both,
    volume 2,618,581 vs 2,639,262) - i.e. Binance revised the trade record
    between when the two archives were generated. Deduping by ID alone
    silently keeps whichever copy happens to be listed first, which is not
    a reliable way to prefer the more authoritative source. The daily
    archive has matched klines almost exactly in every cross-check in this
    audit, so it is treated as authoritative for any day being repaired.

    Returns (trades_with_backfill, still_missing_days) - the latter is
    non-empty only if the daily archive ALSO lacks that day (logged by the
    caller as a genuine, unrecoverable gap).
    """
    still_missing = []
    day_bounds_ms = []
    for day in missing_days:
        day_start = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
        day_start_ms = int(day_start.timestamp() * 1000)
        day_end_ms = day_start_ms + 24 * 60 * 60 * 1000
        day_bounds_ms.append((day_start_ms, day_end_ms))
    if day_bounds_ms:
        keep_mask = pl.lit(True)
        for start_ms, end_ms in day_bounds_ms:
            keep_mask = keep_mask & ~((pl.col("transact_time") >= start_ms) & (pl.col("transact_time") < end_ms))
        frames = [trades.filter(keep_mask)]
    else:
        frames = [trades]
    for day in missing_days:
        date = dt.date(year, month, day)
        url = day_url("aggTrades", symbol, date)
        zip_path = download_and_verify(url, raw_dir / "aggTrades_daily_backfill", manifest)
        if zip_path is None:
            still_missing.append(day)
            continue
        csv_path = extract_single_csv(zip_path, raw_dir / "aggTrades_daily_backfill_extracted")
        day_trades = read_aggtrades(csv_path)
        frames.append(day_trades)
        zip_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
    combined = pl.concat(frames).unique(subset=["agg_trade_id"]).sort("transact_time")
    return combined, still_missing


def read_klines(path: Path) -> pl.DataFrame:
    dtypes = {
        "open_time": pl.Int64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "close_time": pl.Int64,
        "quote_volume": pl.Float64,
        "count": pl.Int64,
        "taker_buy_volume": pl.Float64,
        "taker_buy_quote_volume": pl.Float64,
        "ignore": pl.Utf8,
    }
    df = _read_csv_any_header(path, KLINES_COLUMNS, dtypes)
    df = df.with_columns(normalize_ms(df["open_time"]).alias("open_time"))
    return df


def read_fundingrate(path: Path) -> pl.DataFrame:
    dtypes = {"calc_time": pl.Int64, "funding_interval_hours": pl.Int64, "last_funding_rate": pl.Float64}
    df = _read_csv_any_header(path, FUNDINGRATE_COLUMNS, dtypes)
    df = df.with_columns(normalize_ms(df["calc_time"]).alias("calc_time"))
    return df


def read_bookdepth(path: Path) -> pl.DataFrame:
    dtypes = {"timestamp": pl.Utf8, "percentage": pl.Int64, "depth": pl.Float64, "notional": pl.Float64}
    df = _read_csv_any_header(path, BOOKDEPTH_COLUMNS, dtypes)
    df = df.with_columns(pl.col("timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S").alias("timestamp"))
    return df


def extract_single_csv(zip_path: Path, extract_dir: Path) -> Path:
    import zipfile

    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert len(names) == 1, f"expected exactly 1 file in {zip_path}, got {names}"
        zf.extract(names[0], extract_dir)
        return extract_dir / names[0]
