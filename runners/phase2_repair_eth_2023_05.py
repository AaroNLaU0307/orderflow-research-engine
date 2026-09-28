"""The ETHUSDT 2023-05 same-ID / revised-quantity repair (audit item 47).

This step ran on 2026-07-02 as two inline `python -c` commands in the build
session, not as a committed runner. This file repeats those two commands
exactly. Only a read-only volume check ran between them.

  1. 14:23:22Z: delete data/staging/ETHUSDT/2023-05_{bars,buckets}.parquet,
     then `phase2_backfill_gaps.repair_month("ETHUSDT", 2023, 5, DAYS,
     manifest)` with DAYS below. That uses etl.backfill_missing_days, which
     drops the target days' monthly-archive trades entirely and splices in
     the daily archive's trades. It does not merge by agg_trade_id, because
     on these days the two archives share IDs but disagree on quantity.
     Day 10 is the whole-day gap already repaired by phase2_backfill_gaps.py;
     it is included because the monthly zip is re-read from scratch.
  2. 14:24:14Z: `phase2_etl.finalize_symbol("ETHUSDT", DELTA["ETHUSDT"])`,
     rebuilding data/parquet/ETHUSDT from staging.

The repair result was never appended to data/qa_backfill_log.jsonl. The
ETHUSDT 2023-05 row with `repair_type` AGG_STALE_REVISION was appended by
hand at 14:09:59Z, after an earlier attempt that left out day 10, and its
`result` field describes that attempt. See docs/CORRECTIONS_2026-09-27.md
section 7. This runner does not write to that log.

Proof status (docs/CORRECTIONS_2026-09-27.md section 10): step 2 reproduces
the stored files byte for byte. Step 1 does not, and cannot: the splice does
not fix the order of same-millisecond trades, so two runs on the same zips
differ in `open`/`close` of a few dozen bars and in float summation order.
Since 2026-09-28 (section 12) the splice is deterministic, but it still will
not reproduce the staged file, which was built before that fix.

Modes:
  --verify (default, offline): hash the staged 2023-05 files; rebuild
      data/parquet/ETHUSDT from staging into a temporary directory; compare
      everything with EXPECTED_SHA256. This proves step 2.
  --splice-from DIR (offline): run step 1 on the 12 zips in DIR (the monthly
      zip and the 11 daily zips, named as Binance names them). Each zip must
      match its sha256 and byte size in data/manifest.json before it is used.
      Step 1 runs through the same repair_month / backfill_missing_days code,
      with the download replaced by the verified local copy and staging
      redirected to a temporary directory. The splice runs twice; each
      output is compared with the staged files, by sha256 and, sorted by key,
      column by column. Nothing under data/ is written; the comparison goes
      to reports/eth_2023_05_repair_proof.json. Then runs --verify.
  --execute (network): delete the staged 2023-05 files and redo steps 1 and 2
      in place, downloading through etl.download_and_verify (checked against
      Binance's .CHECKSUM files; it rewrites those URLs' data/manifest.json
      entries), then run --verify.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import phase2_backfill_gaps as bf  # noqa: E402
import phase2_etl as p2  # noqa: E402

import polars as pl  # noqa: E402

from orderflow import etl  # noqa: E402
from orderflow.config import DELTA  # noqa: E402

SYMBOL = "ETHUSDT"
YEAR, MONTH = 2023, 5
DAYS = [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13]

STAGED_BARS = p2.STAGING_DIR / SYMBOL / f"{YEAR:04d}-{MONTH:02d}_bars.parquet"
STAGED_BUCKETS = p2.STAGING_DIR / SYMBOL / f"{YEAR:04d}-{MONTH:02d}_buckets.parquet"

# sha256 of the files on the owner machine, hashed 2026-09-28. The two
# data/parquet files are the ones every Phase 3 runner reads for ETHUSDT.
EXPECTED_SHA256 = {
    "staging/ETHUSDT/2023-05_bars.parquet": "015162b2060788e752aff87df060325bf23c1921403edec6bd3b71366987c093",
    "staging/ETHUSDT/2023-05_buckets.parquet": "00d8d1888f5514d5c1754479513b0d5e40803d71d42d12ffa3f9f99edc53dae3",
    "parquet/ETHUSDT/bars.parquet": "2875bce06420e1271ea9dd78efed8d15d0e786d78f7fe43310f8f2fd494a5253",
    "parquet/ETHUSDT/buckets.parquet": "ebc41b3abe84e90ad57547fefb5eba5c63dbacfe0cae66e6121b9fc16331d0c6",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def execute() -> None:
    STAGED_BARS.unlink(missing_ok=True)
    STAGED_BUCKETS.unlink(missing_ok=True)
    manifest = etl.Manifest.load(bf.MANIFEST_PATH)
    result = bf.repair_month(SYMBOL, YEAR, MONTH, DAYS, manifest)
    print("repair result:", result)
    if result.get("error") or result.get("still_missing"):
        raise SystemExit(f"repair incomplete: {result}")
    p2.finalize_symbol(SYMBOL, DELTA[SYMBOL])


PROOF_REPORT = Path(__file__).resolve().parents[1] / "reports" / "eth_2023_05_repair_proof.json"
SORT_KEYS = {"bars": ["bar_ts_ms"], "buckets": ["bar_ts_ms", "bucket_px"]}


def _splice_once(zip_dir: Path, out_dir: Path) -> dict:
    """repair_month on the local zips, with staging redirected to out_dir."""

    def local_copy(url: str, dest_dir: Path, manifest: etl.Manifest) -> Path:
        # repair_month and backfill_missing_days delete the zip after use,
        # so each call gets a fresh copy of the verified file.
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / url.rsplit("/", 1)[-1]
        shutil.copyfile(zip_dir / dest.name, dest)
        return dest

    saved = (etl.download_and_verify, bf.RAW_DIR, bf.STAGING_DIR)
    etl.download_and_verify = local_copy
    bf.RAW_DIR = out_dir / "raw"
    bf.STAGING_DIR = out_dir / "staging"
    (bf.STAGING_DIR / SYMBOL).mkdir(parents=True)
    try:
        return bf.repair_month(SYMBOL, YEAR, MONTH, DAYS, etl.Manifest(path=out_dir / "unused.json"))
    finally:
        etl.download_and_verify, bf.RAW_DIR, bf.STAGING_DIR = saved


def _content_diff(original: Path, spliced: Path, keys: list[str]) -> dict:
    """Row-order-free comparison: sort both by the key, then compare each column."""
    a = pl.read_parquet(original).sort(keys)
    b = pl.read_parquet(spliced).sort(keys)
    out = {"rows": [a.height, b.height], "keys_equal": a.select(keys).equals(b.select(keys)), "columns": {}}
    if a.shape == b.shape and a.columns == b.columns and out["keys_equal"]:
        for c in a.columns:
            if a[c].equals(b[c]):
                continue
            diff = (a[c].cast(pl.Float64) - b[c].cast(pl.Float64)).abs()
            out["columns"][c] = {"n_rows_differ": int((diff > 0).sum()), "max_abs_diff": float(diff.max())}
    out["identical_after_sort"] = out["keys_equal"] and a.shape == b.shape and not out["columns"]
    return out


def splice_from(zip_dir: Path, runs: int = 2) -> bool:
    """Step 1 on verified local zips, into temporary staging directories.

    Runs the splice `runs` times, to show whether the step itself is
    deterministic, and writes reports/eth_2023_05_repair_proof.json."""
    entries = json.loads(bf.MANIFEST_PATH.read_text(encoding="utf-8"))
    urls = [etl.month_url("aggTrades", SYMBOL, YEAR, MONTH)] + [
        etl.day_url("aggTrades", SYMBOL, dt.date(YEAR, MONTH, d)) for d in DAYS
    ]
    report: dict = {"zips": {}, "runs": []}
    for url in urls:
        entry = entries[url]
        local = zip_dir / url.rsplit("/", 1)[-1]
        match = (entry["status"] == "ok" and local.stat().st_size == entry["byte_size"]
                 and sha256(local) == entry["sha256"])
        report["zips"][local.name] = {"sha256": sha256(local), "matches_manifest": match}
        print(f"{'OK' if match else 'MISMATCH'}  {local.name}")
        if not match:
            print("a zip does not match data/manifest.json; not used")
            PROOF_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return False

    ok = True
    for i in range(runs):
        with tempfile.TemporaryDirectory() as tmp:
            result = _splice_once(zip_dir, Path(tmp))
            run = {"repair_result": result, "files": {}}
            for name, keys in SORT_KEYS.items():
                key = f"staging/ETHUSDT/2023-05_{name}.parquet"
                spliced = Path(tmp) / "staging" / SYMBOL / f"{YEAR:04d}-{MONTH:02d}_{name}.parquet"
                got = sha256(spliced)
                run["files"][key] = {
                    "sha256": got,
                    "byte_identical_to_staged": got == EXPECTED_SHA256[key],
                    "content_vs_staged": _content_diff(p2.STAGING_DIR / SYMBOL / Path(key).name, spliced, keys),
                }
                ok &= got == EXPECTED_SHA256[key]
                print(f"{'OK' if got == EXPECTED_SHA256[key] else 'MISMATCH'}  run {i + 1}: {key}  {got}")
            report["runs"].append(run)
    PROOF_REPORT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {PROOF_REPORT}")
    return ok


def verify() -> bool:
    ok = True
    actual = {
        "staging/ETHUSDT/2023-05_bars.parquet": sha256(STAGED_BARS),
        "staging/ETHUSDT/2023-05_buckets.parquet": sha256(STAGED_BUCKETS),
        "parquet/ETHUSDT/bars.parquet": sha256(p2.PARQUET_DIR / SYMBOL / "bars.parquet"),
        "parquet/ETHUSDT/buckets.parquet": sha256(p2.PARQUET_DIR / SYMBOL / "buckets.parquet"),
    }
    with tempfile.TemporaryDirectory() as tmp:
        saved = p2.PARQUET_DIR
        p2.PARQUET_DIR = Path(tmp)
        try:
            p2.finalize_symbol(SYMBOL, DELTA[SYMBOL])
        finally:
            p2.PARQUET_DIR = saved
        actual["rebuilt from staging: bars.parquet"] = sha256(Path(tmp) / SYMBOL / "bars.parquet")
        actual["rebuilt from staging: buckets.parquet"] = sha256(Path(tmp) / SYMBOL / "buckets.parquet")
    expected = dict(EXPECTED_SHA256)
    expected["rebuilt from staging: bars.parquet"] = EXPECTED_SHA256["parquet/ETHUSDT/bars.parquet"]
    expected["rebuilt from staging: buckets.parquet"] = EXPECTED_SHA256["parquet/ETHUSDT/buckets.parquet"]
    for name, want in expected.items():
        got = actual[name]
        status = "OK" if got == want else "MISMATCH"
        ok &= got == want
        print(f"{status}  {name}  {got}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="offline hash check (default)")
    mode.add_argument("--splice-from", type=Path, metavar="DIR", help="prove step 1 offline from verified zips in DIR")
    mode.add_argument("--execute", action="store_true", help="re-download and redo the repair in place")
    args = parser.parse_args()
    ok = True
    if args.splice_from:
        ok = splice_from(args.splice_from)
    if args.execute:
        execute()
    if not (verify() and ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
