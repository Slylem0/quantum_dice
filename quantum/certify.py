"""Certificación matemática de aleatoriedad a partir de CHSH.

Este módulo separa tres afirmaciones que suelen confundirse:

1. ``h_min_local(S)``: min-entropía de un bit de Alice en UNA ronda CHSH,
   obtenida de la cota de probabilidad de adivinanza. Bajo rondas i.i.d., esta
   min-entropía es aditiva y permite una cuenta finita conservadora.
2. ``h_vn(S)``: entropía condicional de von Neumann por ronda. Es la tasa de
   primer orden que entra en pruebas EAT; no es por sí sola una cota finita.
3. ``certify_iid``: certificado finito bajo SUPUESTOS EXPLÍCITOS i.i.d.,
   memoria por shot y semilla independiente. Usa Hoeffding para bajar S y el
   quantum leftover-hash lemma para fijar la salida Toeplitz.

No afirmamos una prueba EAT completa: el runtime actual ejecuta cuatro circuitos
con ajustes fijos y devuelve histogramas agregados; no implementa spot-checking
secuencial con ajustes aleatorios desconocidos por el dispositivo. La función
``eat_readiness`` hace esta limitación visible en el resultado y en la UI.

Fórmula principal (certificado finito i.i.d.):

    omega_L = omega_hat - sqrt(ln(1/eps_est)/(2*N_test))
    S_L     = 8*omega_L - 4
    k       = n_gen * H_min(A|E, S_L)
    ell     = floor(k - 2*log2(1/eps_ext))

con ``eps_total <= eps_est + eps_ext``. Es conservadora: la versión exacta del
leftover-hash lemma permite una constante aditiva ligeramente mejor.

Referencias:
    - Pironio et al. (2010), Nature 464:1021 (Bell-certified randomness).
    - Masanes, Pironio & Acín (2011), Nat. Commun. 2:238.
    - Tomamichel, Schaffner, Smith & Renner (2011), IEEE TIT 57:5524
      (leftover hashing contra información lateral cuántica).
    - Dupuis, Fawzi & Renner (2020), CMP 379:867 (Entropy Accumulation).
    - Arnon-Friedman, Renner & Vidick (2018), SIAM J. Comput. 48:181
      (protocolos CHSH y EAT).
"""

from __future__ import annotations

import math
from typing import Any

from . import analysis as an
from . import bell

DEFAULT_EPS_EST = 1e-6
DEFAULT_EPS_EXT = 1e-6


def _check_probability(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError(f"{name} debe estar estrictamente entre 0 y 1")
    return value


def _clip_chsh(S: float) -> float:
    S = float(S)
    if not math.isfinite(S):
        raise ValueError("S debe ser finito")
    return min(bell.TSIRELSON, max(an.CLASSICAL_BOUND, S))


def binary_entropy(p: float) -> float:
    """Entropía binaria h2(p), en bits, con tratamiento estable de bordes."""
    p = min(1.0, max(0.0, float(p)))
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def guessing_probability(S: float) -> float:
    """Cota superior de P_guess(A|E) para un bit local dado CHSH=S.

    P_guess <= (1 + sqrt(2 - S^2/4))/2, para 2 <= S <= 2*sqrt(2).
    Valores bajo el límite clásico se tratan como S=2 (sin certificación).
    """
    s = _clip_chsh(S)
    root = math.sqrt(max(0.0, 2.0 - s * s / 4.0))
    return min(1.0, max(0.5, 0.5 * (1.0 + root)))


def h_min_local(S: float) -> float:
    """Min-entropía local H_min(A|E) por ronda, en bits.

    Es ``-log2(P_guess)``: vale 0 en S=2 y 1 en la cota de Tsirelson.
    Esta es la tasa usada por ``certify_iid`` porque la probabilidad de
    adivinanza es multiplicativa para rondas producto (supuesto i.i.d.).
    """
    return -math.log2(guessing_probability(S))


def h_vn(S: float) -> float:
    """Cota de entropía condicional H(A|E) por ronda frente a Eve cuántica.

    H(A|E) >= 1 - h2((1 + sqrt((S/2)^2 - 1))/2).

    Es la tasa de primer orden empleada en análisis EAT/asintóticos. No debe
    multiplicarse por n y llamarse automáticamente min-entropía finita sin una
    prueba EAT/AEP y su corrección de segundo orden.
    """
    s = _clip_chsh(S)
    q = 0.5 * (1.0 + math.sqrt(max(0.0, (s / 2.0) ** 2 - 1.0)))
    return max(0.0, min(1.0, 1.0 - binary_entropy(q)))


def min_tradeoff(S0: float) -> dict[str, float]:
    """Min-tradeoff afín numérica que acota ``h_vn`` por debajo.

    Construye una recta con pendiente local en S0 y baja su intercepto hasta
    quedar bajo h_vn en toda la región [2, 2sqrt(2)]. Es útil como diagnóstico
    y punto de entrada para una implementación EAT futura; NO aplicamos aquí
    una constante de segundo orden no verificada.
    """
    s0 = _clip_chsh(S0)
    step = 1e-5
    lo = max(an.CLASSICAL_BOUND, s0 - step)
    hi = min(bell.TSIRELSON, s0 + step)
    slope = 0.0 if hi == lo else (h_vn(hi) - h_vn(lo)) / (hi - lo)

    # Barrido determinista: desplaza la recta hasta ser una minorante global.
    n_grid = 4096
    intercept = math.inf
    max_gap = 0.0
    for i in range(n_grid + 1):
        s = an.CLASSICAL_BOUND + (bell.TSIRELSON - an.CLASSICAL_BOUND) * i / n_grid
        intercept = min(intercept, h_vn(s) - slope * s)
    for i in range(n_grid + 1):
        s = an.CLASSICAL_BOUND + (bell.TSIRELSON - an.CLASSICAL_BOUND) * i / n_grid
        max_gap = max(max_gap, h_vn(s) - (slope * s + intercept))
    return {
        "S0": s0,
        "slope": slope,
        "intercept": intercept,
        "value_at_S0": max(0.0, slope * s0 + intercept),
        "true_value_at_S0": h_vn(s0),
        "max_gap": max_gap,
    }


def chsh_win_rate(S: float) -> float:
    """Convierte S a probabilidad de ganar el juego CHSH: omega=(S+4)/8."""
    return min(1.0, max(0.0, (float(S) + 4.0) / 8.0))


def chsh_lower_bound(S_hat: float, n_test: int, eps_est: float = DEFAULT_EPS_EST) -> dict[str, float]:
    """Cota unilateral de Hoeffding para el score CHSH verdadero.

    Para N_test indicadores de victoria independientes en [0,1], con
    probabilidad al menos 1-eps_est:

        omega >= omega_hat - sqrt(ln(1/eps_est)/(2*N_test)).

    La hipótesis de independencia/i.i.d. se expone explícitamente en el
    certificado. Esta función no pretende cubrir dispositivos con memoria.
    """
    if int(n_test) != n_test or n_test <= 0:
        raise ValueError("n_test debe ser un entero positivo")
    eps_est = _check_probability("eps_est", eps_est)
    omega_hat = chsh_win_rate(S_hat)
    delta = math.sqrt(math.log(1.0 / eps_est) / (2.0 * n_test))
    omega_lower = max(0.0, omega_hat - delta)
    S_lower_raw = 8.0 * omega_lower - 4.0
    return {
        "omega_hat": omega_hat,
        "omega_lower": omega_lower,
        "hoeffding_delta": delta,
        "S_lower_raw": S_lower_raw,
        "S_lower": max(an.CLASSICAL_BOUND, min(bell.TSIRELSON, S_lower_raw)),
        "eps_est": eps_est,
        "n_test": int(n_test),
        "certifies_violation": bool(S_lower_raw > an.CLASSICAL_BOUND),
    }


def extractor_output_length(min_entropy_bits: float, eps_ext: float = DEFAULT_EPS_EXT) -> int:
    """Longitud conservadora de salida para hashing Toeplitz 2-universal.

    Usamos ``ell=floor(k-2*log2(1/eps_ext))``. La forma exacta
    ``floor(k-2*log2(1/(2*Delta)))`` gana 2 bits; omitimos esa constante para
    ser conservadores y mantener una interpretación simple de eps_ext.
    """
    eps_ext = _check_probability("eps_ext", eps_ext)
    k = float(min_entropy_bits)
    if not math.isfinite(k) or k <= 0.0:
        return 0
    return max(0, int(math.floor(k - 2.0 * math.log2(1.0 / eps_ext))))


def eat_readiness(*, randomized_settings: bool, per_shot_memory: bool, sequential_inputs: bool) -> dict[str, Any]:
    """Audita si los datos satisfacen los requisitos estructurales para EAT."""
    missing = []
    if not randomized_settings:
        missing.append("ajustes CHSH aleatorios por ronda")
    if not per_shot_memory:
        missing.append("resultados individuales por shot")
    if not sequential_inputs:
        missing.append("entradas elegidas después de iniciar cada ronda")
    return {
        "ready": not missing,
        "missing": missing,
        "note": (
            "EAT listo: aún falta fijar y revisar la constante de segundo orden."
            if not missing
            else "No se reclama seguridad EAT: el lote actual no implementa spot-checking secuencial."
        ),
    }


def certify_iid(
    n_generation: int,
    S_hat: float,
    n_test: int,
    eps_est: float = DEFAULT_EPS_EST,
    eps_ext: float = DEFAULT_EPS_EXT,
    *,
    per_shot_memory: bool = True,
    independent_extractor_seed: bool = False,
) -> dict[str, Any]:
    """Certificado finito bajo supuestos i.i.d. explícitos.

    La salida es extraíble solo si existe la cadena por shot y la semilla del
    Toeplitz es pública e independiente. Si falta cualquiera, calculamos el
    presupuesto matemático pero ``certified_bits`` se fija en 0 para no afirmar
    que el histograma agregado o una semilla determinista son salida segura.
    """
    if int(n_generation) != n_generation or n_generation < 0:
        raise ValueError("n_generation debe ser un entero no negativo")
    stats = chsh_lower_bound(S_hat, n_test, eps_est)
    s_lower = stats["S_lower"]
    rate = h_min_local(s_lower) if stats["certifies_violation"] else 0.0
    entropy_total = n_generation * rate
    budget = extractor_output_length(entropy_total, eps_ext)
    blockers = []
    if not stats["certifies_violation"]:
        blockers.append("la cota finita de S no supera 2")
    if not per_shot_memory:
        blockers.append("el backend no devolvió memoria por shot")
    if not independent_extractor_seed:
        blockers.append("la semilla Toeplitz no es independiente")
    extractable = not blockers
    eps_ext = _check_probability("eps_ext", eps_ext)
    eps_total = float(eps_est) + eps_ext
    return {
        "framework": "finite_iid_chsh_local_min_entropy",
        "security_model": "i.i.d. rounds + finite Hoeffding parameter estimation + quantum-proof leftover hashing",
        "composable_within_stated_model": True,
        "eat_claimed": False,
        "h_min_per_round": rate,
        "h_vn_first_order_rate": h_vn(s_lower) if stats["certifies_violation"] else 0.0,
        "rounds": int(n_generation),
        "test_rounds": int(n_test),
        "total_min_entropy": entropy_total,
        "extractor_budget_bits": budget,
        "certified_bits": budget if extractable else 0,
        "extractable": extractable,
        "blockers": blockers,
        "eps_est": float(eps_est),
        "eps_ext": eps_ext,
        "eps_total": eps_total,
        "S_observed": float(S_hat),
        "S_lower": stats["S_lower"],
        "S_lower_raw": stats["S_lower_raw"],
        "omega_hat": stats["omega_hat"],
        "omega_lower": stats["omega_lower"],
        "finite_size_penalty_bits": max(0.0, n_generation * h_min_local(S_hat) - entropy_total),
        "parameter_estimation": stats,
        "extractor_seed_independent": bool(independent_extractor_seed),
        "per_shot_memory": bool(per_shot_memory),
        "security_margin": None,
        "explanation": (
            "Salida certificada dentro del modelo i.i.d. declarado."
            if extractable
            else "Se calculó el presupuesto de entropía, pero no se etiqueta como salida certificada: "
                 + "; ".join(blockers)
        ),
    }


def certify(
    n_rounds: int,
    S_obs: float,
    eps_s: float = DEFAULT_EPS_EST,
    eps_ext: float = DEFAULT_EPS_EXT,
    *,
    n_test: int | None = None,
    per_shot_memory: bool = True,
    independent_extractor_seed: bool = False,
) -> dict[str, Any]:
    """Alias público compatible con el handoff; usa la cota finita i.i.d.

    ``eps_s`` se interpreta como fallo de estimación ``eps_est``. El nombre se
    conserva para la API planeada, pero el resultado deja ``eat_claimed=False``.
    """
    return certify_iid(
        n_rounds,
        S_obs,
        n_test if n_test is not None else 4 * max(1, n_rounds),
        eps_est=eps_s,
        eps_ext=eps_ext,
        per_shot_memory=per_shot_memory,
        independent_extractor_seed=independent_extractor_seed,
    )
