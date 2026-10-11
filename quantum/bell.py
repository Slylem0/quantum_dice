"""Test CHSH sobre un par de Bell: la fuente de la aleatoriedad certificada.

Un par |Phi+> = (|00> + |11>)/sqrt(2) se mide en 4 combinaciones de ángulos
(ajustes de Alice a0/a1 y de Bob b0/b1). El valor CHSH es

    S = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)

donde E(a,b) = <A_a B_b> es el correlador. Para |Phi+> con los ángulos óptimos
(Alice 0 y pi/2; Bob pi/4 y -pi/4) el valor ideal es S = 2*sqrt(2) ~ 2.828
(cota de Tsirelson). El límite clásico/local es S <= 2: superarlo es la prueba
de que los resultados no estaban predeterminados.

Medición en un ángulo t: observable cos(t) Z + sin(t) X, que se lee aplicando
RY(-t) y midiendo en Z. Los 4 circuitos salen en UN solo backend.run (IonQ
permite un único job por ejecución).

Bit order (Qiskit little-endian), registro ``out``: clbit 0 = Alice, 1 = Bob.

Referencias:
    - Clauser, Horne, Shimony & Holt (1969). Phys. Rev. Lett. 23:880.
    - Tsirelson (1980). Lett. Math. Phys. 4:93.
"""

from __future__ import annotations

import math
from typing import Any

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

from . import analysis as an

# Ángulos óptimos para |Phi+> (en radianes).
ALICE = (0.0, math.pi / 2)
BOB = (math.pi / 4, -math.pi / 4)

# Los 4 ajustes (i de Alice, j de Bob) y el signo con el que entran en S.
# S = E00 + E01 + E10 - E11.
SETTINGS = ((0, 0, +1), (0, 1, +1), (1, 0, +1), (1, 1, -1))

TSIRELSON = 2.0 * math.sqrt(2.0)
CLASSICAL_BOUND = an.CLASSICAL_BOUND


def _name(i: int, j: int) -> str:
    return f"chsh_a{i}_b{j}"


def _measure_at_angle(qc: QuantumCircuit, qubit: Any, angle: float) -> None:
    """Prepara la medida del observable a 'angle': RY(-angle) y luego Z."""
    if angle != 0.0:
        qc.ry(-angle, qubit)


def build_chsh() -> list[QuantumCircuit]:
    """Los 4 circuitos CHSH de un par de Bell (uno por ajuste a_i, b_j)."""
    circuits = []
    for i, j, _sign in SETTINGS:
        a, b = QuantumRegister(1, "A"), QuantumRegister(1, "B")
        out = ClassicalRegister(2, "out")
        qc = QuantumCircuit(a, b, out, name=_name(i, j), metadata={"a": i, "b": j})
        # Preparar |Phi+>.
        qc.h(a[0])
        qc.cx(a[0], b[0])
        # Rotar a la base de medición de cada parte.
        _measure_at_angle(qc, a[0], ALICE[i])
        _measure_at_angle(qc, b[0], BOB[j])
        qc.measure(a[0], out[0])
        qc.measure(b[0], out[1])
        circuits.append(qc)
    return circuits


def theory_chsh() -> dict[str, float]:
    """Correladores y S teóricos de |Phi+> con los ángulos óptimos."""
    e = {}
    for i, j, _ in SETTINGS:
        # <A_a B_b> = cos(a - b) para |Phi+> con observables en el plano X-Z.
        e[(i, j)] = math.cos(ALICE[i] - BOB[j])
    s = sum(sign * e[(i, j)] for i, j, sign in SETTINGS)
    return {"E": e, "S": s, "tsirelson": TSIRELSON, "classical_bound": CLASSICAL_BOUND}


def decode_chsh(counts_by_id: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Calcula S (con IC95) y los 4 correladores a partir de los counts.

    Devuelve ``{S, S_ci95, sigma, significance_sigma, correlators, theory,
    violates}``. El IC de S usa varianzas Agresti-Coull (no colapsan en los
    bordes). ``significance_sigma`` = (S - 2) / sigma: a cuántas sigmas está la
    violación del límite clásico.
    """
    th = theory_chsh()
    corr = {}
    terms = []
    wins = 0
    game_rounds = 0
    per_setting_wins = {}
    for i, j, sign in SETTINGS:
        c = an.correlator(counts_by_id[_name(i, j)], [0, 1])
        corr[f"E_a{i}_b{j}"] = {
            "value": c["value"],
            "ci95": c["ci95"],
            "theory": th["E"][(i, j)],
            "shots": c["shots"],
        }
        # Juego CHSH: para los tres términos positivos se gana con paridad 0;
        # para el término negativo (a1,b1), con paridad 1.
        setting_wins = round(c["shots"] * ((1.0 - c["p_odd"]) if sign > 0 else c["p_odd"]))
        per_setting_wins[f"a{i}_b{j}"] = int(setting_wins)
        wins += int(setting_wins)
        game_rounds += int(c["shots"])
        terms.append((sign, c))
    s = sum(sign * c["value"] for sign, c in terms)
    var = sum(an.ac_var(c) for _sign, c in terms)
    sigma = math.sqrt(var)
    half = 1.96 * sigma
    return {
        "S": s,
        "S_ci95": [s - half, s + half],
        "sigma": sigma,
        "significance_sigma": (s - an.CLASSICAL_BOUND) / sigma if sigma > 0 else None,
        "correlators": corr,
        "game": {
            "wins": wins,
            "rounds": game_rounds,
            "win_rate": wins / game_rounds if game_rounds else 0.0,
            "S_from_win_rate": 8.0 * wins / game_rounds - 4.0 if game_rounds else -4.0,
            "per_setting_wins": per_setting_wins,
        },
        "theory": {"S": th["S"], "tsirelson": th["tsirelson"], "classical_bound": th["classical_bound"]},
        "violates": bool((s - half) > an.CLASSICAL_BOUND),
    }
