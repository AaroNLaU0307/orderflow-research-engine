"""Binance USD-M futures full-depth L2 order book diff recorder.

Deliverable in lieu of confirmatory H4 (liquidity wall) / H5 (liquidity
pull) testing in v1 - the official Binance historical archive has no
full-depth L2 history (only the aggregated bookDepth summary), and paid
third-party vendors' free tiers (e.g. Tardis, 1st-of-month-only) are too
sparse for a confirmatory event study. This collector lets live L2
recording start now, accumulating toward a future v1.5 in which H4/H5 can
be tested confirmatorily on self-recorded data. See
preregistration/PREREGISTRATION.md section 3.

Implements Binance's documented diff-depth synchronization procedure
(https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-market-streams/Diff-Book-Depth-Streams):
1. Open the @depth@100ms websocket stream and buffer incoming events.
2. Fetch a REST snapshot (GET /fapi/v1/depth) - this can race arbitrarily
   with step 1, which is why step 1 starts first and buffers.
3. Discard any buffered event with u <= snapshot.lastUpdateId (stale).
4. The first event to apply is the one where U <= lastUpdateId+1 <= u.
5. Apply that and every subsequent event in order. USD-M futures (unlike
   spot) carries a `pu` field ("previous final update ID") specifically
   for continuity checking: each event's pu must equal the previous
   event's u, or the stream has gapped and needs a fresh resync (logged,
   not auto-retried in this v1 collector - see ROADMAP.md for v1.5
   hardening). Verified empirically during smoke testing: the naive
   spot-style check (event[i].U == event[i-1].u + 1) falsely flags nearly
   every event as a gap on a perfectly healthy futures stream, since
   consecutive futures diff events are not required to be U-contiguous
   the way spot ones are - pu is the correct field for this market.

Restart-safe by construction: every run performs its own fresh
snapshot+resync, so a crash or restart only costs the resync gap (a few
seconds), never corrupted or ambiguous on-disk state - each flushed
parquet file is a self-contained, already-ordered chunk of diff events.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path

import polars as pl
import requests
import websockets

WS_BASE = "wss://fstream.binance.com/stream"
REST_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_sync_index(pending: list[dict], snapshot_last_update_id: int) -> int | None:
    """Index of the first buffered event to apply after a REST snapshot,
    per Binance's documented procedure: the event where
    U <= lastUpdateId+1 <= u. Assumes `pending` is already filtered to
    events with u > snapshot_last_update_id (stale ones dropped)."""
    return next((i for i, e in enumerate(pending) if e["U"] <= snapshot_last_update_id + 1 <= e["u"]), None)


def is_continuous(event: dict, prev_final_update_id: int | None) -> bool:
    """USD-M futures continuity check: event['pu'] must equal the previous
    event's 'u'. Unlike spot, futures diff events are not required to be
    U-contiguous (U == prev.u + 1) - that check falsely flags nearly every
    event on a healthy futures stream (verified empirically)."""
    if prev_final_update_id is None:
        return True
    return event.get("pu") == prev_final_update_id


class DepthRecorder:
    def __init__(self, symbol: str, out_dir: Path, flush_every: int = 500):
        self.symbol = symbol.upper()
        self.out_dir = out_dir
        self.flush_every = flush_every
        self.buffer: list[dict] = []
        self.snapshot_last_update_id: int | None = None
        self.synced = False
        self.prev_final_update_id: int | None = None
        self.n_recorded = 0
        self.n_gaps = 0

    def fetch_snapshot(self) -> dict:
        resp = requests.get(REST_DEPTH_URL, params={"symbol": self.symbol, "limit": 1000}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _record_event(self, event: dict) -> None:
        self.buffer.append(
            {
                "event_time_ms": event["E"],
                "transact_time_ms": event.get("T", event["E"]),
                "first_update_id": event["U"],
                "final_update_id": event["u"],
                "prev_final_update_id": event.get("pu"),
                "bids": json.dumps(event["b"]),
                "asks": json.dumps(event["a"]),
            }
        )
        self.n_recorded += 1

    def _flush(self) -> None:
        if not self.buffer:
            return
        df = pl.DataFrame(self.buffer)
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{self.symbol}_depth_{ts}.parquet"
        df.write_parquet(path)
        log(f"  flushed {len(self.buffer)} events -> {path.name}")
        self.buffer.clear()

    async def run(self, max_events: int | None = None, max_seconds: float | None = None) -> int:
        stream = f"{self.symbol.lower()}@depth@100ms"
        url = f"{WS_BASE}?streams={stream}"
        deadline = time.monotonic() + max_seconds if max_seconds is not None else None
        pending: list[dict] = []

        log(f"Connecting to {url}")
        async with websockets.connect(url) as ws:
            snapshot_task = asyncio.create_task(asyncio.to_thread(self.fetch_snapshot))
            while not snapshot_task.done():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    pending.append(json.loads(msg)["data"])
                except asyncio.TimeoutError:
                    continue
            snapshot = snapshot_task.result()
            self.snapshot_last_update_id = snapshot["lastUpdateId"]
            log(f"Snapshot lastUpdateId={self.snapshot_last_update_id}, {len(pending)} events buffered during fetch")

            pending = [e for e in pending if e["u"] > self.snapshot_last_update_id]
            sync_idx = find_sync_index(pending, self.snapshot_last_update_id)
            if sync_idx is not None:
                for e in pending[sync_idx:]:
                    self._record_event(e)
                self.synced = True
                self.prev_final_update_id = pending[-1]["u"]
                log(f"Synced from buffered events at index {sync_idx}")

            while True:
                if max_events is not None and self.n_recorded >= max_events:
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    break
                try:
                    timeout = 2.0
                    if deadline is not None:
                        timeout = max(0.1, min(timeout, deadline - time.monotonic()))
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    continue
                event = json.loads(msg)["data"]

                if not self.synced:
                    if event["u"] <= self.snapshot_last_update_id:
                        continue
                    if event["U"] <= self.snapshot_last_update_id + 1 <= event["u"]:
                        self.synced = True
                    else:
                        continue
                elif not is_continuous(event, self.prev_final_update_id):
                    self.n_gaps += 1
                    log(f"  GAP: expected pu={self.prev_final_update_id}, got pu={event.get('pu')} (not auto-resynced in v1)")

                self._record_event(event)
                self.prev_final_update_id = event["u"]
                if len(self.buffer) >= self.flush_every:
                    self._flush()

        self._flush()
        log(f"Recorded {self.n_recorded} events, {self.n_gaps} gap(s) detected.")
        return self.n_recorded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--max-events", type=int, default=None, help="stop after N events (smoke-testing)")
    parser.add_argument("--max-seconds", type=float, default=None, help="stop after N seconds (smoke-testing)")
    parser.add_argument("--flush-every", type=int, default=500)
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parents[1] / "data" / "depth" / args.symbol.upper()
    recorder = DepthRecorder(args.symbol, out_dir, flush_every=args.flush_every)
    n = asyncio.run(recorder.run(max_events=args.max_events, max_seconds=args.max_seconds))
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
