"""Estadística y utilidades compartidas (puras, vectorizadas con NumPy).

Convención de Qiskit: little-endian. En una cadena de bits de counts, el
carácter de más a la derecha es el clbit 0.

Referencias:
    - Wilson, E. B. (1927). JASA 22(158):209 (intervalo score).
    - Agresti & Coull (1998). Am. Stat. 52:119.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

Counts = dict[str, int]

# Límite clásico/local del test CHSH: cualquier teoría de variables ocultas
# locales cumple S <= 2. Superarlo es la firma de la no-localidad cuántica.
CLASSICAL_BOUND = 2.0


# --------------------------------------------------------------------------
# Parseo de counts
# --------------------------------------------------------------------------

def _key_to_int(key: str) -> int:
    k = key.replace(" ", "")
    if k.lower().startswith("0x"):
        return int(k, 16)
    return int(k, 2)


def bits_from_counts(counts: Counts, n_clbits: int) -> tuple[NDArray[np.uint8], NDArray[np.int64]]:
    """Parsea counts a una matriz de bits [K, n_clbits] y pesos por fila.

    La columna j es el clbit j (carácter -1-j de la clave, little-endian).
    """
    keys = list(counts)
    values = np.array([_key_to_int(k) for k in keys], dtype=np.int64)
    weights = np.array([int(counts[k]) for k in keys], dtype=np.int64)
    shifts = np.arange(n_clbits, dtype=np.int64)
    bits = ((values[:, None] >> shifts[None, :]) & 1).astype(np.uint8)
    return bits, weights


def parity(bits: NDArray[np.uint8], indices: Iterable[int]) -> NDArray[np.uint8]:
    """XOR de las columnas seleccionadas (un valor por fila)."""
    idx = list(indices)
    if not idx:
        return np.zeros(bits.shape[0], dtype=np.uint8)
    return np.bitwise_xor.reduce(bits[:, idx], axis=1)


# --------------------------------------------------------------------------
# Intervalos de confianza
# --------------------------------------------------------------------------

def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción binomial k/n (n=0 -> [0,1])."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# --------------------------------------------------------------------------
# Correladores
# --------------------------------------------------------------------------

def correlator(counts: Counts, indices: Sequence[int]) -> dict[str, Any]:
    """Estima <AB> = 1 - 2q a partir de la paridad de los clbits dados.

    q es la fracción de shots con paridad 1. Devuelve value, var, ci95, shots.
    """
    all_idx = list(indices)
    n_bits = max(all_idx + [0]) + 1
    bits, w = bits_from_counts(counts, n_bits)
    n = int(w.sum())
    odd = parity(bits, all_idx).astype(bool)
    k = float(w[odd].sum())
    q = k / n if n > 0 else 0.5
    lo, hi = wilson(k, n)
    return {
        "value": 1.0 - 2.0 * q,
        "var": 4.0 * q * (1.0 - q) / n if n > 0 else 1.0,
        "ci95": [1.0 - 2.0 * hi, 1.0 - 2.0 * lo],
        "shots": n,
        "p_odd": q,
    }


def ac_var(c: dict[str, Any]) -> float:
    """Varianza Agresti-Coull de un correlador (no colapsa a 0 en los bordes)."""
    n = c.get("shots")
    if not n:
        return float(c["var"])
    k = n * (1.0 - c["value"]) / 2.0
    q = (k + 2.0) / (n + 4.0)
    return 4.0 * q * (1.0 - q) / (n + 4.0)


# --------------------------------------------------------------------------
# JSON helper
# --------------------------------------------------------------------------

def _plain(obj: Any) -> Any:
    """Convierte NumPy / tuplas a tipos JSON planos; no-finitos -> None."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _plain(obj.tolist())
    if isinstance(obj, np.generic):
        return _plain(obj.item())
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


to_plain = _plain


def is_ionq(backend: Any) -> bool:
    return type(backend).__module__.startswith("qiskit_ionq") or "ionq" in backend_name(backend).lower()


def backend_name(backend: Any) -> str:
    name = getattr(backend, "name", None)
    if callable(name):
        name = name()
    return str(name) if name else type(backend).__name__
