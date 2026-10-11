"""Tests del certificado finito, extractor Toeplitz y auditoría EAT."""

import json
import math

import numpy as np
import pytest

from quantum import certify as cert
from quantum import randomness

TS = 2 * math.sqrt(2)


def test_entropy_bounds_and_monotonicity():
    assert cert.h_min_local(2.0) == pytest.approx(0.0, abs=1e-12)
    assert cert.h_min_local(TS) == pytest.approx(1.0, abs=1e-9)
    assert cert.h_vn(2.0) == pytest.approx(0.0, abs=1e-12)
    assert cert.h_vn(TS) == pytest.approx(1.0, abs=1e-9)
    grid = np.linspace(2.0, TS, 101)
    for fn in (cert.h_min_local, cert.h_vn):
        vals = [fn(float(s)) for s in grid]
        assert all(a <= b + 1e-12 for a, b in zip(vals, vals[1:]))
        assert all(0 <= v <= 1 for v in vals)


def test_hoeffding_lower_bound_is_conservative_and_improves_with_n():
    small = cert.chsh_lower_bound(2.75, 1_000, eps_est=1e-6)
    large = cert.chsh_lower_bound(2.75, 100_000, eps_est=1e-6)
    assert small["S_lower_raw"] < large["S_lower_raw"] < 2.75
    assert small["hoeffding_delta"] > large["hoeffding_delta"]


def test_leftover_hash_output_length():
    assert cert.extractor_output_length(0, 1e-6) == 0
    expected = math.floor(1000 - 2 * math.log2(1 / 1e-6))
    assert cert.extractor_output_length(1000, 1e-6) == expected
    assert cert.extractor_output_length(10, 1e-12) == 0


def test_finite_certificate_exposes_assumptions_and_eps():
    out = cert.certify_iid(
        100_000,
        2.8,
        400_000,
        eps_est=1e-6,
        eps_ext=1e-6,
        per_shot_memory=True,
        independent_extractor_seed=True,
    )
    assert out["extractable"] and out["certified_bits"] > 0
    assert out["certified_bits"] <= out["total_min_entropy"]
    assert out["eps_total"] == pytest.approx(2e-6)
    assert out["eat_claimed"] is False
    assert out["S_lower"] < out["S_observed"]
    json.dumps(out)


def test_certificate_blocks_missing_memory_or_seed():
    no_mem = cert.certify_iid(10_000, 2.8, 40_000, per_shot_memory=False,
                              independent_extractor_seed=True)
    no_seed = cert.certify_iid(10_000, 2.8, 40_000, per_shot_memory=True,
                               independent_extractor_seed=False)
    assert no_mem["certified_bits"] == 0 and not no_mem["extractable"]
    assert no_seed["certified_bits"] == 0 and not no_seed["extractable"]
    assert "memoria" in " ".join(no_mem["blockers"])
    assert "semilla" in " ".join(no_seed["blockers"])


def test_eat_readiness_is_honest():
    current = cert.eat_readiness(
        randomized_settings=False, per_shot_memory=True, sequential_inputs=False
    )
    assert not current["ready"] and len(current["missing"]) == 2
    future = cert.eat_readiness(
        randomized_settings=True, per_shot_memory=True, sequential_inputs=True
    )
    assert future["ready"]


def _toeplitz_direct(bits, out_len, seed_bits):
    n = len(bits)
    out = []
    for i in range(out_len):
        total = 0
        for j, bit in enumerate(bits):
            total ^= (seed_bits[n - 1 + i - j] & bit)
        out.append(total)
    return out


def test_fft_toeplitz_matches_direct_gf2():
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, 53).tolist()
    out_len = 31
    seed_bits = rng.integers(0, 2, len(bits) + out_len - 1).tolist()
    fast = randomness.toeplitz_extract(bits, out_len, seed_bits=seed_bits)
    assert fast == _toeplitz_direct(bits, out_len, seed_bits)


def test_min_tradeoff_is_global_lower_bound_on_grid():
    trade = cert.min_tradeoff(2.6)
    for s in np.linspace(2, TS, 1001):
        line = trade["slope"] * s + trade["intercept"]
        assert line <= cert.h_vn(float(s)) + 1e-9
