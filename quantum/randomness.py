"""De la violación de Bell a bits aleatorios certificados.

Pipeline:
    1. Bits crudos: de los shots del circuito CHSH ``a0_b0`` (ajuste de
       generación) tomamos el resultado de Alice como bit crudo por ronda.
    2. Certificación: a partir del valor S estimado derivamos la MIN-ENTROPY por
       ronda, es decir cuántos bits de aleatoriedad genuina garantiza la física
       (cota tipo Pironio et al. 2010). -> ``min_entropy_from_S`` (MODELO POTENTE)
    3. Extracción: un extractor (Toeplitz / leftover hash) comprime los bits
       crudos a bits casi uniformes, en número = floor(n_rondas * H_min) menos un
       margen de seguridad. -> ``toeplitz_extract`` (MODELO POTENTE)

Las dos piezas marcadas [MODELO POTENTE] traen una implementación PROVISIONAL y
CONSERVADORA (suficiente para que el proyecto corra y la demo funcione), con la
derivación rigurosa pendiente de validar/afinar por un modelo matemático
potente. Cada una lleva una nota ``# TODO(modelo-potente)`` con exactamente qué
debe revisarse.

Convención de bits: little-endian de Qiskit. En el circuito CHSH, clbit 0 =
Alice, clbit 1 = Bob.
"""

from __future__ import annotations

import math
import secrets
from typing import Any, Sequence

import numpy as np

from . import analysis as an
from . import bell
from . import certify as cert

# Circuito cuyo resultado de Alice usamos como fuente de bits crudos.
# (Ajuste a0,b0: el de generación en el protocolo estándar.)
GEN_CIRCUIT = "chsh_a0_b0"
ALICE_CLBIT = 0


# --------------------------------------------------------------------------
# 1. Bits crudos
# --------------------------------------------------------------------------

def raw_bits(counts: dict[str, int], clbit: int = ALICE_CLBIT, max_bits: int = 100000) -> list[int]:
    """Serialización CANÓNICA de un histograma; solo para diagnóstico.

    ``counts`` perdió el orden por shot. Expandir sus multiplicidades permite
    calcular sesgo o mostrar una vista previa, pero NO reconstruye la cadena
    cuántica original y no debe entrar al extractor certificado. Para eso se
    usa ``shot_memory_bits``.
    """
    bits_mat, w = an.bits_from_counts(counts, clbit + 1)
    col = bits_mat[:, clbit]
    out: list[int] = []
    for value, count in zip(col.tolist(), w.tolist()):
        if len(out) >= max_bits:
            break
        take = min(int(count), max_bits - len(out))
        out.extend([int(value)] * take)
    return out


def shot_memory_bits(memory: Sequence[str], clbit: int = ALICE_CLBIT, max_bits: int = 100000) -> list[int]:
    """Extrae la cadena real por shot de Qiskit ``Result.get_memory``.

    En little-endian, clbit 0 es el carácter derecho. Rechaza claves inválidas
    en vez de inventar bits.
    """
    out = []
    for raw in memory[:max_bits]:
        key = str(raw).replace(" ", "")
        if key.lower().startswith("0x"):
            value = int(key, 16)
            out.append((value >> clbit) & 1)
        else:
            if not key or any(c not in "01" for c in key) or clbit >= len(key):
                raise ValueError(f"resultado de memoria inválido: {raw!r}")
            out.append(int(key[-1 - clbit]))
    return out


def bit_bias(bits: Sequence[int]) -> dict[str, Any]:
    """Sesgo observado de los bits crudos: P(1), desvío de 0.5, test rápido."""
    n = len(bits)
    if n == 0:
        return {"n": 0, "p1": 0.0, "bias": 0.0}
    p1 = sum(bits) / n
    return {"n": n, "p1": p1, "bias": abs(p1 - 0.5)}


# --------------------------------------------------------------------------
# 2. Certificación: cota CHSH finita y explícita
# --------------------------------------------------------------------------

def min_entropy_from_S(S: float) -> float:
    """Compatibilidad: min-entropía local de un bit, delegada en certify.py."""
    return cert.h_min_local(S)


def certified_bits(
    n_rounds: int,
    S: float,
    security_margin: float | None = None,
    *,
    n_test: int | None = None,
    eps_est: float = cert.DEFAULT_EPS_EST,
    eps_ext: float = cert.DEFAULT_EPS_EXT,
    per_shot_memory: bool = True,
    independent_extractor_seed: bool = True,
) -> dict[str, Any]:
    """Presupuesto finito i.i.d. sin margen heurístico.

    ``security_margin`` se conserva solo para compatibilidad y se ignora; el
    resultado lo marca como ``None``. La penalización real viene de la cota
    unilateral de Hoeffding sobre S y del quantum leftover-hash lemma.
    """
    del security_margin
    return cert.certify_iid(
        n_rounds,
        S,
        n_test if n_test is not None else 4 * max(1, n_rounds),
        eps_est,
        eps_ext,
        per_shot_memory=per_shot_memory,
        independent_extractor_seed=independent_extractor_seed,
    )


# --------------------------------------------------------------------------
# 3. Extractor Toeplitz 2-universal
# --------------------------------------------------------------------------

def toeplitz_extract(
    bits: Sequence[int],
    out_len: int,
    seed: int = 0,
    *,
    seed_bits: Sequence[int] | None = None,
) -> list[int]:
    """Hash Toeplitz 2-universal sobre GF(2), acelerado por convolución FFT.

    Una matriz m×n necesita n+m-1 bits de semilla pública independiente.
    ``seed_bits`` permite entregarlos explícitamente. ``seed`` genera una
    semilla determinista solo para pruebas/demos y NO debe etiquetarse como
    independiente en un certificado de seguridad.

    La longitud ``out_len`` debe venir de ``cert.extractor_output_length``.
    """
    n = len(bits)
    if n == 0 or out_len <= 0:
        return []
    out_len = min(int(out_len), n)
    x = np.asarray(bits, dtype=np.int8) & 1
    need = n + out_len - 1
    if seed_bits is None:
        rng = np.random.default_rng(seed)
        diagonal = rng.integers(0, 2, size=need, dtype=np.int8)
    else:
        diagonal = np.asarray(seed_bits, dtype=np.int8) & 1
        if diagonal.size != need:
            raise ValueError(f"seed_bits debe tener {need} bits (recibió {diagonal.size})")

    # T[i,j] = diagonal[n-1+i-j]. La convolución diagonal*x evaluada en
    # n-1+i produce exactamente la suma de la fila i. FFT reduce O(n*m) a
    # O((n+m) log(n+m)); redondeamos antes de tomar paridad.
    size = need + n - 1
    fft_len = 1 << (size - 1).bit_length()
    conv = np.fft.irfft(
        np.fft.rfft(diagonal.astype(float), fft_len)
        * np.fft.rfft(x.astype(float), fft_len),
        fft_len,
    )
    sums = np.rint(conv[n - 1 : n - 1 + out_len]).astype(np.int64)
    return (sums & 1).astype(np.int8).tolist()


def independent_seed_bits(length: int) -> list[int]:
    """Semilla pública independiente para Toeplitz desde el CSPRNG del runtime.

    La semilla no necesita ser secreta y un extractor fuerte permite publicarla;
    sí debe ser uniforme e independiente de la cadena cuántica. En Pyodide,
    ``secrets`` delega en la fuente criptográfica del navegador/runtime.
    """
    if length <= 0:
        return []
    return [secrets.randbits(1) for _ in range(length)]


# --------------------------------------------------------------------------
# Empaquetado del resultado (contrato JSON para la UI)
# --------------------------------------------------------------------------

def _bits_to_hex(bits: Sequence[int]) -> str:
    if not bits:
        return ""
    s = "".join(str(b) for b in bits)
    s = s + "0" * ((4 - len(s) % 4) % 4)
    return "".join(f"{int(s[i:i+4], 2):x}" for i in range(0, len(s), 4))


def _dice_rolls(bits: Sequence[int], n: int = 5) -> list[int]:
    """Convierte bits en 'tiradas de dado' (1-6) por rechazo (demo visual)."""
    rolls: list[int] = []
    i = 0
    while len(rolls) < n and i + 3 <= len(bits):
        v = (bits[i] << 2) | (bits[i + 1] << 1) | bits[i + 2]
        i += 3
        if v < 6:  # 0..5 -> rechazo de 6,7 para uniformidad
            rolls.append(v + 1)
    return rolls


def summarize(
    counts: dict[str, dict[str, int]],
    decoded: dict[str, Any],
    seed: int = 0,
    *,
    memory: dict[str, list[str]] | None = None,
    use_independent_seed: bool = True,
) -> dict[str, Any]:
    """Certifica y extrae únicamente cuando existe memoria por shot.

    El histograma siempre se conserva para CHSH y diagnóstico de sesgo. La
    salida Toeplitz requiere la secuencia original (`memory`) y una semilla
    pública independiente; de lo contrario se devuelve un presupuesto, pero
    cero bits etiquetados como certificados.
    """
    S = decoded["S"]
    diagnostic = raw_bits(counts[GEN_CIRCUIT])
    memory_available = bool(memory and GEN_CIRCUIT in memory)
    raw = shot_memory_bits(memory[GEN_CIRCUIT]) if memory_available else []
    source_for_bias = raw if raw else diagnostic
    bias = bit_bias(source_for_bias)
    n_generation = len(raw) if raw else int(sum(counts[GEN_CIRCUIT].values()))
    n_test = int(decoded.get("game", {}).get("rounds", 4 * max(1, n_generation)))
    cert_result = certified_bits(
        n_generation,
        S,
        n_test=n_test,
        per_shot_memory=memory_available,
        independent_extractor_seed=bool(use_independent_seed),
    )

    extracted: list[int] = []
    extractor_seed_source = "none"
    if cert_result["extractable"] and cert_result["certified_bits"] > 0:
        out_len = min(cert_result["certified_bits"], len(raw))
        if use_independent_seed:
            seed_material = independent_seed_bits(len(raw) + out_len - 1)
            extracted = toeplitz_extract(raw, out_len, seed_bits=seed_material)
            extractor_seed_source = "runtime_csprng_public_independent"
        else:  # modo determinista de desarrollo; certify_iid lo bloquea
            extracted = toeplitz_extract(raw, out_len, seed=seed)
            extractor_seed_source = "deterministic_demo_only"
    ext_bias = bit_bias(extracted)
    # Las tiradas certificadas solo salen de extracted; sin extracción segura no
    # inventamos una tirada "certificada" desde el histograma.
    rolls = _dice_rolls(extracted)

    readiness = cert.eat_readiness(
        randomized_settings=False,
        per_shot_memory=memory_available,
        sequential_inputs=False,
    )
    viz = {
        "S": S,
        "S_ci95": decoded["S_ci95"],
        "S_lower": cert_result["S_lower"],
        "classical_bound": an.CLASSICAL_BOUND,
        "tsirelson": bell.TSIRELSON,
        "violates": decoded["violates"],
        "finite_certificate": cert_result["extractable"],
        "significance_sigma": decoded["significance_sigma"],
        "h_min_per_round": cert_result["h_min_per_round"],
        "h_vn_first_order_rate": cert_result["h_vn_first_order_rate"],
        "eps_total": cert_result["eps_total"],
        "finite_size_penalty_bits": cert_result["finite_size_penalty_bits"],
        "raw_bias": bias["bias"],
        "extracted_bias": ext_bias["bias"],
        "rolls": rolls,
        "raw_preview": raw[:64],
        "extracted_preview": extracted[:64],
        "eat_readiness": readiness,
    }
    return {
        "S": S,
        "certification": cert_result,
        "raw_bits": {
            "n": len(raw),
            "available": memory_available,
            "p1": bias["p1"] if memory_available else None,
            "bias": bias["bias"] if memory_available else None,
            "hex": _bits_to_hex(raw[:256]),
            "histogram_bias_diagnostic": bit_bias(diagnostic),
        },
        "extracted_bits": {
            "n": len(extracted),
            "p1": ext_bias["p1"] if extracted else None,
            "bias": ext_bias["bias"] if extracted else None,
            "hex": _bits_to_hex(extracted[:256]),
            "seed_source": extractor_seed_source,
        },
        "dice_rolls": rolls,
        "eat_readiness": readiness,
        "viz": viz,
    }
