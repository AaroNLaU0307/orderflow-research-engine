import hashlib
import json
from pathlib import Path

import pytest

from orderflow import etl

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
RECENT = SAMPLE / "extracted"
OLD = SAMPLE / "old_extracted"

pytestmark = pytest.mark.skipif(not RECENT.exists(), reason="Phase 0 sample files not present on this machine")


def test_sniff_header_present_recent_era():
    assert etl.sniff_header(RECENT / "aggTrades" / "BTCUSDT-aggTrades-2025-03-17.csv") is True
    assert etl.sniff_header(RECENT / "klines" / "BTCUSDT-1m-2025-03-17.csv") is True


def test_sniff_header_absent_old_era():
    assert etl.sniff_header(OLD / "aggTrades" / "BTCUSDT-aggTrades-2022-07-01.csv") is False
    assert etl.sniff_header(OLD / "klines" / "BTCUSDT-1m-2022-07-01.csv") is False


def test_read_aggtrades_normalizes_both_eras_to_same_schema():
    recent = etl.read_aggtrades(RECENT / "aggTrades" / "BTCUSDT-aggTrades-2025-03-17.csv")
    old = etl.read_aggtrades(OLD / "aggTrades" / "BTCUSDT-aggTrades-2022-07-01.csv")
    assert recent.columns == old.columns == etl.AGGTRADES_COLUMNS
    assert recent.schema == old.schema
    # both eras are ms-epoch; spot check a known value from the 2022-07-01 file
    assert old["transact_time"][0] == 1656633600033


def test_read_klines_normalizes_both_eras():
    recent = etl.read_klines(RECENT / "klines" / "BTCUSDT-1m-2025-03-17.csv")
    old = etl.read_klines(OLD / "klines" / "BTCUSDT-1m-2022-07-01.csv")
    assert recent.columns == old.columns == etl.KLINES_COLUMNS
    assert old.height == 1440
    assert recent.height == 1440


def test_read_fundingrate():
    fr = etl.read_fundingrate(RECENT / "fundingRate" / "BTCUSDT-fundingRate-2025-03.csv")
    assert fr.columns == etl.FUNDINGRATE_COLUMNS
    assert fr["funding_interval_hours"].unique().to_list() == [8]


def test_read_bookdepth():
    bd = etl.read_bookdepth(RECENT / "bookDepth" / "BTCUSDT-bookDepth-2025-03-17.csv")
    assert bd.columns == etl.BOOKDEPTH_COLUMNS
    assert set(bd["percentage"].unique().to_list()) == {-5, -4, -3, -2, -1, 1, 2, 3, 4, 5}


@pytest.mark.parametrize(
    "sample_int,expected_unit",
    [
        (1656633600033, "milliseconds"),
        (1656633600, "seconds"),
        (1656633600033000, "microseconds"),
        (1656633600033000000, "nanoseconds"),
    ],
)
def test_sniff_ts_unit(sample_int, expected_unit):
    assert etl.sniff_ts_unit(sample_int) == expected_unit


def test_aggtrades_klines_volume_reconciliation_within_tolerance():
    """Reproduces the Phase 0 QA sanity check as a permanent regression test."""
    trades = etl.read_aggtrades(RECENT / "aggTrades" / "BTCUSDT-aggTrades-2025-03-17.csv")
    kl = etl.read_klines(RECENT / "klines" / "BTCUSDT-1m-2025-03-17.csv")
    agg_vol = trades["quantity"].sum()
    kl_vol = kl["volume"].sum()
    diff_pct = abs(agg_vol - kl_vol) / kl_vol * 100
    assert diff_pct < 0.5


def test_manifest_records_and_detects_prior_ingestion(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    m = etl.Manifest.load(manifest_path)
    assert not m.already_ingested("http://example/x.zip")
    m.record("http://example/x.zip", sha256="abc123", byte_size=100)
    assert m.already_ingested("http://example/x.zip")

    reloaded = etl.Manifest.load(manifest_path)
    assert reloaded.already_ingested("http://example/x.zip")
    assert reloaded.entries["http://example/x.zip"]["sha256"] == "abc123"


def test_checksum_mismatch_detected(tmp_path):
    content = b"hello world"
    dest = tmp_path / "file.zip"
    dest.write_bytes(content)
    wrong_checksum = hashlib.sha256(b"not the right content").hexdigest()
    checksum_path = tmp_path / "file.zip.CHECKSUM"
    checksum_path.write_text(f"{wrong_checksum}  file.zip\n")

    actual = etl._sha256_of(dest)
    assert actual != wrong_checksum

    correct_checksum = hashlib.sha256(content).hexdigest()
    checksum_path.write_text(f"{correct_checksum}  file.zip\n")
    assert etl._sha256_of(dest) == correct_checksum
