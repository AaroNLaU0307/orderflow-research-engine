import sys
from pathlib import Path

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
