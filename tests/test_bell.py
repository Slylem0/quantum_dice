"""Tests de la física CHSH y del pipeline de aleatoriedad."""

import json
import math

import pytest
from qiskit.providers.basic_provider import BasicSimulator

from quantum import api, bell, randomness
from quantum import analysis as an

OPTS = {"seed_simulator": 7}


def _run_counts(shots=4000):
    circuits = bell.build_chsh()
    from quantum.execute import run_batch
    return run_batch(BasicSimulator(), circuits, shots, **OPTS)


def test_build_chsh_four_circuits():
    cs = bell.build_chsh()
    assert len(cs) == 4
    names = {c.name for c in cs}
    assert names == {"chsh_a0_b0", "chsh_a0_b1", "chsh_a1_b0", "chsh_a1_b1"}
    for c in cs:
        assert c.num_qubits == 2 and c.num_clbits == 2


def test_theory_is_tsirelson():
    th = bell.theory_chsh()
    assert th["S"] == pytest.approx(2 * math.sqrt(2), abs=1e-9)
    assert th["classical_bound"] == 2.0


def test_chsh_violates_on_ideal_simulator():
    counts = _run_counts(6000)
    dec = bell.decode_chsh(counts)
    # S debe acercarse a 2sqrt2 ~ 2.828 y violar claramente el 2.
    assert dec["S"] == pytest.approx(2 * math.sqrt(2), abs=0.12)
    assert dec["S"] > 2.0
    assert dec["violates"] is True
    assert dec["significance_sigma"] > 3.0
    # Los 4 correladores cerca de +-1/sqrt(2).
    for key, c in dec["correlators"].items():
        assert c["ci95"][0] <= c["theory"] <= c["ci95"][1] + 1e-9


def test_min_entropy_monotonic_and_bounds():
    assert randomness.min_entropy_from_S(2.0) == pytest.approx(0.0, abs=1e-9)
    assert randomness.min_entropy_from_S(2 * math.sqrt(2)) == pytest.approx(1.0, abs=1e-9)
    # Monótona creciente en [2, 2sqrt2].
    xs = [2.0, 2.2, 2.4, 2.6, 2.8, 2 * math.sqrt(2)]
    hs = [randomness.min_entropy_from_S(s) for s in xs]
    assert all(hs[i] <= hs[i + 1] + 1e-12 for i in range(len(hs) - 1))


def test_toeplitz_extract_shapes_and_binary():
    bits = [0, 1, 1, 0, 1, 0, 0, 1] * 20
    out = randomness.toeplitz_extract(bits, 50, seed=1)
    assert len(out) == 50
    assert set(out) <= {0, 1}
    # Determinista con la misma semilla.
    assert out == randomness.toeplitz_extract(bits, 50, seed=1)
    # Distinta semilla -> (casi seguro) distinto.
    assert out != randomness.toeplitz_extract(bits, 50, seed=2)


def test_certified_bits_zero_at_classical():
    c2 = randomness.certified_bits(1000, 2.0)
    assert c2["certified_bits"] == 0
    cmax = randomness.certified_bits(1000, 2 * math.sqrt(2))
    assert cmax["certified_bits"] > 0


def test_api_roll_envelope_and_json():
    out = api.roll(BasicSimulator(), 2000, **OPTS)
    assert out["ok"] is True
    assert out["chsh"]["S"] > 2.0
    assert out["certification"]["certified_bits"] >= 0
    assert "viz" in out and "rolls" in out["viz"]
    assert all(1 <= r <= 6 for r in out["dice_rolls"])
    json.dumps(out)  # debe ser JSON-serializable


def test_api_roll_handles_no_backend():
    out = api.roll(None)
    assert out["ok"] is False and out["error"]


def test_api_info():
    i = api.info()
    assert i["ok"] and i["tsirelson"] == pytest.approx(2 * math.sqrt(2))
