"""results/headline.json must match the committed artifacts it cites. Every
stat is recomputed here from its artifact (CSV/config-backed) or found
verbatim in it (markdown-backed); no licensed data is needed.
"""
import json
import re
from pathlib import Path

import polars as pl
import pytest

from orderflow import config, stats

ROOT = Path(__file__).resolve().parents[1]
HEADLINE = json.loads((ROOT / "results" / "headline.json").read_text(encoding="utf-8"))
CELLS_CSV = "reports/event_study_btc_cells.csv"

TOP_KEYS = {"schema", "repo", "source_commit", "as_of", "rows"}
ROW_KEYS = {"id", "section", "hypothesis", "verdict", "verdict_detail", "mechanism", "stats", "caveats"}
STAT_KEYS = {"label", "display", "value", "artifact", "locator", "provenance"}
PROVENANCE = {"reproduced", "repo-reported, not reproduced", "predates fix; pending re-run"}

ALL_STATS = [s for row in HEADLINE["rows"] for s in row["stats"]]


def _cells() -> pl.DataFrame:
    return pl.read_csv(ROOT / CELLS_CSV)


def _min_bh_adjusted_q(p_values: list[float]) -> float:
    """Smallest Benjamini-Hochberg adjusted q, cross-checked against the
    repo's own bh_fdr: it rejects nothing just below this level and
    something just above it."""
    ranked = sorted(p_values)
    q = min(p * len(ranked) / rank for rank, p in enumerate(ranked, start=1))
    assert not any(stats.bh_fdr(p_values, q=q * (1 - 1e-9)))
    assert any(stats.bh_fdr(p_values, q=q * (1 + 1e-9)))
    return q


def _max_n_events(signal: str) -> int:
    return int(_cells().filter(pl.col("signal") == signal)["n_events"].max())


def _best_cell_mean_bp() -> float:
    # runners/phase5_final_report.py: highest mean among cells with raw p < 0.05
    nominal = _cells().filter(pl.col("p_value") < 0.05)
    assert nominal.select(["signal", "horizon_bars"]).rows() == [("H1", 6), ("H1", 12)]
    return float(nominal.sort("observed_mean_bp", descending=True)["observed_mean_bp"][0])


# label -> (recompute, display formatter, tolerance on value)
RECOMPUTE = {
    "BH-FDR significant cells (q = 0.10)": (
        lambda: sum(stats.bh_fdr(_cells()["p_value"].to_list(), q=config.FDR_Q)),
        lambda v: f"{v}/{_cells().height}",
        0,
    ),
    "smallest BH-adjusted q": (lambda: _min_bh_adjusted_q(_cells()["p_value"].to_list()), lambda v: f"{v:.3f}", 1e-6),
    "best cell gross mean (H1, 1h)": (_best_cell_mean_bp, lambda v: f"{v:.1f} bp", 1e-4),
    "materiality bar (gate 3)": (lambda: config.MATERIALITY_BP, lambda v: f"{v:g} bp", 0),
    "round-trip cost": (lambda: config.ROUND_TRIP_BP, lambda v: f"{v:g} bp", 0),
    "H3 in-sample events": (lambda: _max_n_events("H3"), str, 0),
    "H6 in-sample events": (lambda: _max_n_events("H6"), str, 0),
}


def test_schema_keys():
    assert set(HEADLINE) == TOP_KEYS
    assert HEADLINE["schema"] == "headline/v1"
    assert HEADLINE["repo"] == "AaroNLaU0307/orderflow-research-engine"
    assert re.fullmatch(r"[0-9a-f]{40}|PENDING", HEADLINE["source_commit"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", HEADLINE["as_of"])
    assert HEADLINE["rows"]
    for row in HEADLINE["rows"]:
        assert set(row) == ROW_KEYS
        assert row["section"] in {"archive", "other"}
        assert row["stats"] and all(isinstance(c, str) for c in row["caveats"])
        for stat in row["stats"]:
            assert set(stat) == STAT_KEYS
            assert stat["provenance"] in PROVENANCE


@pytest.mark.parametrize("stat", ALL_STATS, ids=[s["label"] for s in ALL_STATS])
def test_stat_artifact_exists(stat):
    assert (ROOT / stat["artifact"]).is_file()


@pytest.mark.parametrize("stat", ALL_STATS, ids=[s["label"] for s in ALL_STATS])
def test_stat_matches_artifact(stat):
    if stat["artifact"].endswith(".md"):
        assert stat["display"] in (ROOT / stat["artifact"]).read_text(encoding="utf-8")
        assert stat["value"] == int(stat["display"].replace(",", ""))
        return
    assert stat["label"] in RECOMPUTE, f"no recomputation registered for {stat['label']!r}"
    recompute, fmt, tol = RECOMPUTE[stat["label"]]
    recomputed = recompute()
    assert abs(recomputed - stat["value"]) <= tol
    assert fmt(recomputed) == stat["display"]
