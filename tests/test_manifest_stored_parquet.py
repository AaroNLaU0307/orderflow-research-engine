"""data/manifest.json pins the stored parquet the runners read (section stored_parquet).

The zip entries are keyed by URL and pin the raw archives; the stored_parquet section pins
data/parquet/{BTCUSDT,ETHUSDT}/{bars,buckets}.parquet, the bytes every runner reads
(docs/CORRECTIONS_2026-09-27.md section 12). The hash check needs the local data store,
so it is marked ``data`` and skipped when the files are absent.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
STORED = {f"data/parquet/{s}/{f}.parquet" for s in ("BTCUSDT", "ETHUSDT") for f in ("bars", "buckets")}


def test_stored_parquet_section_lists_the_four_files():
    section = MANIFEST["stored_parquet"]
    assert set(section) == STORED
    for entry in section.values():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert entry["byte_size"] > 0


def test_every_other_key_is_a_zip_entry():
    for key, entry in MANIFEST.items():
        if key == "stored_parquet":
            continue
        assert key.startswith("https://data.binance.vision/"), key
        assert entry["status"] in {"ok", "missing_404", "CHECKSUM_MISMATCH"}, key


@pytest.mark.data
@pytest.mark.parametrize("rel", sorted(STORED))
def test_stored_parquet_matches_its_recorded_hash(rel):
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not present (the ~54GB data store is not committed)")
    entry = MANIFEST["stored_parquet"][rel]
    assert path.stat().st_size == entry["byte_size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
