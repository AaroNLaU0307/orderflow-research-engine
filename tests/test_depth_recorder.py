import asyncio
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from depth_recorder import DepthRecorder, find_sync_index, is_continuous  # noqa: E402


def test_find_sync_index_picks_the_straddling_event():
    pending = [
        {"U": 100, "u": 105},
        {"U": 106, "u": 110},
        {"U": 111, "u": 120},
    ]
    # snapshot lastUpdateId=108 -> need U<=109<=u -> event 1 (U=106,u=110) straddles 109
    assert find_sync_index(pending, snapshot_last_update_id=108) == 1


def test_find_sync_index_none_when_no_straddle():
    pending = [{"U": 200, "u": 210}]
    assert find_sync_index(pending, snapshot_last_update_id=50) is None


def test_is_continuous_first_event_always_true():
    assert is_continuous({"pu": 12345}, prev_final_update_id=None) is True


def test_is_continuous_matching_pu():
    assert is_continuous({"pu": 500}, prev_final_update_id=500) is True


def test_is_continuous_detects_gap():
    assert is_continuous({"pu": 600}, prev_final_update_id=500) is False


def test_is_continuous_does_not_use_spot_style_U_check():
    """Regression test for the bug found during smoke-testing: the
    spot-market check (event.U == prev.u + 1) falsely flags nearly every
    event on a healthy USD-M futures stream. A continuous futures event
    can have U far from prev.u+1 as long as pu matches."""
    event = {"U": 999_999, "u": 1_000_050, "pu": 500}  # U wildly discontinuous
    assert is_continuous(event, prev_final_update_id=500) is True


def test_record_event_and_flush(tmp_path):
    recorder = DepthRecorder("BTCUSDT", tmp_path, flush_every=2)
    recorder._record_event({"E": 1000, "T": 1001, "U": 1, "u": 5, "pu": None, "b": [["100", "1"]], "a": [["101", "2"]]})
    assert recorder.n_recorded == 1
    assert len(recorder.buffer) == 1
    recorder._flush()
    assert len(recorder.buffer) == 0
    files = list(tmp_path.glob("*.parquet"))
    assert len(files) == 1

    import polars as pl

    df = pl.read_parquet(files[0])
    assert df.height == 1
    assert df["final_update_id"][0] == 5


class _FakeDepthStream:
    """Stands in for the websocket: serves the given messages, then behaves
    like an idle stream (recv times out) - no network."""

    def __init__(self, messages: list[str]):
        self._messages = list(messages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self) -> str:
        await asyncio.sleep(0.01)
        if self._messages:
            return self._messages.pop(0)
        raise asyncio.TimeoutError


def test_run_persists_rest_snapshot_book(tmp_path, monkeypatch):
    """The REST snapshot is the starting book the diffs are applied to; a
    level resting unchanged after it never appears in a diff, so the
    snapshot itself (not just its lastUpdateId) must be written to disk."""
    snapshot = {
        "lastUpdateId": 108,
        "E": 1_000,
        "T": 999,
        "bids": [["100.0", "1.5"], ["99.9", "2.0"]],
        "asks": [["100.1", "0.7"]],
    }
    diffs = [
        {"E": 1_001, "T": 1_000, "U": 100, "u": 105, "pu": 99, "b": [], "a": []},  # stale: u <= 108
        {"E": 1_002, "T": 1_001, "U": 106, "u": 110, "pu": 105, "b": [["100.0", "0"]], "a": []},  # straddles 109
        {"E": 1_003, "T": 1_002, "U": 111, "u": 120, "pu": 110, "b": [], "a": [["100.2", "3.0"]]},
    ]
    messages = [json.dumps({"stream": "btcusdt@depth@100ms", "data": d}) for d in diffs]
    monkeypatch.setattr("websockets.connect", lambda url: _FakeDepthStream(messages))
    recorder = DepthRecorder("BTCUSDT", tmp_path, flush_every=500)
    monkeypatch.setattr(recorder, "fetch_snapshot", lambda: snapshot)

    n = asyncio.run(recorder.run(max_events=2, max_seconds=5))

    assert n == 2
    snapshot_files = list(tmp_path.glob("BTCUSDT_snapshot_*.parquet"))
    assert len(snapshot_files) == 1
    saved = pl.read_parquet(snapshot_files[0])
    assert saved.height == 1
    row = saved.row(0, named=True)
    assert row["last_update_id"] == 108
    assert json.loads(row["bids"]) == snapshot["bids"]
    assert json.loads(row["asks"]) == snapshot["asks"]
    assert (row["event_time_ms"], row["transact_time_ms"]) == (1_000, 999)
    diffs_saved = pl.concat([pl.read_parquet(f) for f in tmp_path.glob("BTCUSDT_depth_*.parquet")])
    assert diffs_saved["first_update_id"].to_list() == [106, 111]
