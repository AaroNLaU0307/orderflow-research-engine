"""Matplotlib figure generation for README (report-only visualization,
never a gating input - preregistration defines no figure-based decision).

Agg backend (headless-safe, no display required). Fixed figsize/dpi so
output is visually consistent across regenerations. Every function here
takes already-loaded DataFrames/arrays and an output path, deliberately
free of any file I/O beyond writing the PNG - this makes them unit-testable
against small synthetic fixtures without the real downloaded dataset (see
tests/test_figures.py). runners/phase5_figures.py is the thin script that
reads the real report CSVs and BTC bar store and calls these.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

FIGSIZE = (10, 6)
FIGSIZE_WIDE = (13, 6)
DPI = 150

HORIZON_LABELS = {1: "5m", 3: "15m", 6: "30m", 12: "1h", 48: "4h"}
SIGNALS_ORDER = ["H1", "H2", "H3", "H6"]
HORIZONS_ORDER = [1, 3, 6, 12, 48]
SIGNAL_COLORS = {"H1": "#1f77b4", "H2": "#ff7f0e", "H3": "#2ca02c", "H6": "#d62728"}


def _cell_order_index(signal: str, horizon: int) -> int:
    return SIGNALS_ORDER.index(signal) * len(HORIZONS_ORDER) + HORIZONS_ORDER.index(horizon)


def make_fig1_forest(cells_df: pl.DataFrame, materiality_bp: float, round_trip_bp: float, out_path) -> None:
    """20-cell forest plot: mean signed gross return (bp) with 95% CI,
    grouped by signal, shared linear y-axis (H3's wide CIs are the point -
    underpowered should look underpowered, not be axis-scaled away)."""
    rows = sorted(
        cells_df.iter_rows(named=True), key=lambda r: _cell_order_index(r["signal"], r["horizon_bars"])
    )
    xs, means, err_lo, err_hi, colors, xticklabels = [], [], [], [], [], []
    x = 0.0
    prev_signal = None
    group_centers: dict[str, list[float]] = {s: [] for s in SIGNALS_ORDER}
    for row in rows:
        if prev_signal is not None and row["signal"] != prev_signal:
            x += 1.0  # gap between signal groups
        xs.append(x)
        group_centers[row["signal"]].append(x)
        means.append(row["observed_mean_bp"])
        err_lo.append(row["observed_mean_bp"] - row["ci95_lo_bp"])
        err_hi.append(row["ci95_hi_bp"] - row["observed_mean_bp"])
        colors.append("#d62728" if row["bh_significant_q10"] else "#1f77b4")
        xticklabels.append(HORIZON_LABELS[row["horizon_bars"]])
        prev_signal = row["signal"]
        x += 1.0

    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE, dpi=DPI)
    ax.axhspan(-round_trip_bp, round_trip_bp, color="orange", alpha=0.08, label=f"round-trip cost floor (~{round_trip_bp:g}bp)")
    ax.axhspan(-materiality_bp, materiality_bp, color="red", alpha=0.12, label=f"economic materiality bar ({materiality_bp:g}bp = 1.5x round-trip cost)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.errorbar(
        xs, means, yerr=[err_lo, err_hi], fmt="o", markersize=5, capsize=3, color="#1f77b4", ecolor="#1f77b4", linewidth=1.2,
    )
    for xi, mi, ci in zip(xs, means, colors):
        if ci == "#d62728":
            ax.plot(xi, mi, "o", markersize=6, color=ci, zorder=5)
    ax.set_xticks(xs)
    ax.set_xticklabels(xticklabels, fontsize=8)
    blended = ax.get_xaxis_transform()  # x in data coords, y in axes-fraction coords
    for sig, centers in group_centers.items():
        if centers:
            ax.text(sum(centers) / len(centers), -0.11, sig, transform=blended, ha="center", va="top", fontweight="bold", fontsize=11)
    ax.set_ylabel("Mean signed gross forward return (bp)")
    ax.set_title("BTC in-sample event study: 20 cells (4 signals x 5 horizons), 95% CI\nNo cell is BH-FDR significant at q=0.10 (2,000,000-rep day-cluster bootstrap)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.margins(x=0.02)
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)


def make_fig2_bh_step(cells_df: pl.DataFrame, fdr_q: float, out_path) -> None:
    """Classic Benjamini-Hochberg step-up plot: sorted raw p-values (rank on
    x, log y) against the i/n * q threshold line."""
    rows = sorted(cells_df.iter_rows(named=True), key=lambda r: r["rank_by_p"])
    ranks = [r["rank_by_p"] for r in rows]
    pvals = [r["p_value"] for r in rows]
    thresholds = [r["operative_bh_threshold"] for r in rows]

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    ax.plot(ranks, thresholds, "-", color="gray", linewidth=1.2, label=f"BH threshold: rank/{len(rows)} * {fdr_q}")
    ax.plot(ranks, pvals, "o", color="#1f77b4", markersize=6, label="observed raw p-value (2,000,000 reps)")
    ax.set_yscale("log")
    ax.set_xlabel("Rank (ascending by raw p-value)")
    ax.set_ylabel("p-value (log scale)")
    ax.set_title("BH-FDR step-up procedure, 20-cell BTC in-sample family (q=0.10)\nNo point falls on or below the threshold line - verdict seed-invariant across 3 seeds")

    rank1 = next(r for r in rows if r["rank_by_p"] == 1)
    rank2 = next(r for r in rows if r["rank_by_p"] == 2)
    ax.annotate(
        f"rank 1: {rank1['signal']}@{rank1['horizon_bars']} p={rank1['p_value']:.4f} vs thr={rank1['operative_bh_threshold']:.3f}",
        xy=(1, rank1["p_value"]), xytext=(2.3, rank1["p_value"] * 1.6),
        arrowprops=dict(arrowstyle="->", color="black", lw=0.8), fontsize=8,
    )
    ax.annotate(
        f"rank 2: {rank2['signal']}@{rank2['horizon_bars']} p={rank2['p_value']:.4f} vs thr={rank2['operative_bh_threshold']:.3f}",
        xy=(2, rank2["p_value"]), xytext=(3.3, rank2["p_value"] * 0.55),
        arrowprops=dict(arrowstyle="->", color="black", lw=0.8), fontsize=8,
    )
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)


def make_fig3_sensitivity_heatmap(primary_cells_df: pl.DataFrame, sensitivity_df: pl.DataFrame, out_path) -> None:
    """Rows = primary config + 4 sensitivity configs, columns = 20 signal x
    horizon cells, value = t-stat, diverging colormap centered at 0,
    |t|>1.96 cells marked."""
    config_order = ["primary_5m_delta25", "delta10_bar5m", "delta50_bar5m", "bar3m_delta25", "bar15m_delta25"]
    config_labels = {
        "primary_5m_delta25": "primary (5m, d=25)",
        "delta10_bar5m": "d=10 (5m)",
        "delta50_bar5m": "d=50 (5m)",
        "bar3m_delta25": "3m (d=25)",
        "bar15m_delta25": "15m (d=25)",
    }
    cols = [(s, h) for s in SIGNALS_ORDER for h in HORIZONS_ORDER]
    col_index = {c: i for i, c in enumerate(cols)}

    matrix = np.full((len(config_order), len(cols)), np.nan)
    for row in primary_cells_df.iter_rows(named=True):
        matrix[0, col_index[(row["signal"], row["horizon_bars"])]] = row["t_stat"]
    for row in sensitivity_df.iter_rows(named=True):
        r = config_order.index(row["config"])
        matrix[r, col_index[(row["signal"], row["horizon_bars"])]] = row["t_stat"]

    vmax = np.nanmax(np.abs(matrix))
    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE, dpi=DPI)
    im = ax.imshow(matrix, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    sig_rows, sig_cols = np.where(np.abs(matrix) > 1.96)
    ax.scatter(sig_cols, sig_rows, marker="o", s=40, facecolors="none", edgecolors="black", linewidths=1.3, label="|t|>1.96")

    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"{s}\n{HORIZON_LABELS[h]}" for s, h in cols], fontsize=7)
    ax.set_yticks(range(len(config_order)))
    ax.set_yticklabels([config_labels[c] for c in config_order], fontsize=9)
    ax.set_title(
        "t-statistic across primary + 4 sensitivity configs (80+20 cells, all report-only/uncorrected except primary row)\n"
        "8/80 sensitivity cells cross |t|>1.96 vs ~4 expected by chance; the only cross-config recurrence\n"
        "(H1 under d=10/d=50) is mechanical duplication of the same d-independent event set"
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("t-statistic")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)


def select_fig4_window(events_df: pl.DataFrame, window_ms: int) -> tuple[int, int]:
    """Deterministic window-selection rule (states explicitly what it does,
    not left to run() to interpret): candidates are the sorted, unique
    bar_ts (epoch ms) of every event in `events_df` (any signal); for each
    candidate W in ascending order, check whether the half-open window
    [W, W+window_ms) contains at least one event of every distinct signal
    present in `events_df`; return the first (earliest) W that qualifies,
    as (window_start_ms, window_end_ms). Cannot cherry-pick outcomes: the
    rule only ever looks at event *timestamps*, never at any forward
    return, so no return-related information can influence which window is
    chosen.
    """
    signals_present = set(events_df["signal"].unique().to_list())
    if not signals_present:
        raise ValueError("no events to select a window from")
    ts_by_signal = {
        sig: np.sort(events_df.filter(pl.col("signal") == sig)["bar_ts"].dt.epoch(time_unit="ms").to_numpy())
        for sig in signals_present
    }
    candidates = np.sort(events_df["bar_ts"].dt.epoch(time_unit="ms").unique().to_numpy())
    for w in candidates:
        w = int(w)
        end = w + window_ms
        if all(np.any((arr >= w) & (arr < end)) for arr in ts_by_signal.values()):
            return w, end
    raise ValueError(f"no {window_ms}ms window in the given events contains all of {sorted(signals_present)}")


def make_fig4_signal_examples(bars: pl.DataFrame, events_df: pl.DataFrame, window_start_ms: int, window_end_ms: int, out_path) -> None:
    """BTC 5m close price over one IS window with event markers for all
    four signals (color = signal, marker shape = direction). Displays only
    detections, no forward returns - see select_fig4_window's docstring for
    why the window choice cannot be outcome-cherry-picked."""
    win_bars = bars.filter(
        (pl.col("bar_ts").dt.epoch(time_unit="ms") >= window_start_ms)
        & (pl.col("bar_ts").dt.epoch(time_unit="ms") < window_end_ms)
    ).sort("bar_index")
    win_events = events_df.filter(
        (pl.col("bar_ts").dt.epoch(time_unit="ms") >= window_start_ms)
        & (pl.col("bar_ts").dt.epoch(time_unit="ms") < window_end_ms)
    )

    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE, dpi=DPI)
    ax.plot(win_bars["bar_ts"].to_list(), win_bars["close"].to_list(), color="black", linewidth=0.9, label="BTC 5m close")

    close_by_bar_index = dict(zip(win_bars["bar_index"].to_list(), win_bars["close"].to_list()))
    plotted_labels = set()
    for row in win_events.iter_rows(named=True):
        price = close_by_bar_index.get(row["bar_index"])
        if price is None:
            continue
        marker = "^" if row["direction"] == 1 else "v"
        label = row["signal"] if row["signal"] not in plotted_labels else None
        plotted_labels.add(row["signal"])
        ax.plot(row["bar_ts"], price, marker=marker, markersize=8, color=SIGNAL_COLORS[row["signal"]], linestyle="none", label=label, zorder=5)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    ax.set_ylabel("BTC close (USDT)")
    ax.set_title("Earliest 7-day IS window containing >=1 event of every signal (detections only, no returns shown)")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
