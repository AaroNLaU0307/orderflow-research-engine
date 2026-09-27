"""Pins the source of every statistics helper in orderflow.stats, so a silent
edit to a function that produced the published p-values, CIs or BH-FDR
calls fails CI. After an intentional edit, update the hash below and say
why in the commit message (see the provenance header in
src/orderflow/stats.py).
"""
import hashlib
import inspect

import pytest

from orderflow import config, stats

PINNED_SHA256 = {
    "stable_seed": "d91ef9f56562f1b8c2227e9212f40b25ef1c404d9bc2c1f1d3d822ab455350c1",
    "day_cluster_bootstrap_mean": "05c2e769be81ec7c41e1a78cd9915aa99da5a7c0ac5f3bda008fef26ff085db0",
    "day_cluster_bootstrap_spearman": "f89dc3618c6df630248c8c1e7b79efb8bd927a0717819f4ef85b4ec5b18b76ed",
    "circular_shift_placebo": "998d4f47aa3d242dec3ee02d7be1632db2ebf4dea9be706e50e7e72377776c6b",
    "bh_fdr": "b873fc8b2504b506b84cf816ad49bf21749bcb6583e1d377ef25b741745bdbb8",
}


def _normalised_source_sha256(func) -> str:
    source = "\n".join(line.rstrip() for line in inspect.getsource(func).splitlines())
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("name", sorted(PINNED_SHA256))
def test_stats_helper_source_is_pinned(name):
    assert _normalised_source_sha256(getattr(stats, name)) == PINNED_SHA256[name], (
        f"orderflow.stats.{name} changed; update PINNED_SHA256 deliberately if the change is intended"
    )


def test_every_public_stats_function_is_pinned():
    public = {n for n, f in inspect.getmembers(stats, inspect.isfunction) if f.__module__ == stats.__name__ and not n.startswith("_")}
    assert public == set(PINNED_SHA256)


def test_bh_default_level_matches_study_fdr_q():
    assert inspect.signature(stats.bh_fdr).parameters["q"].default == 0.10
    assert config.FDR_Q == 0.10
