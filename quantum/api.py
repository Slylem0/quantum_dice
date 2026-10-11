"""Fachada JS-facing: funciones simples, resultados en dict plano.

Cada función que corre circuitos toma ``backend`` como argumento (Qollab lo
crea). Devuelve ``{"ok": True, ...}`` o ``{"ok": False, "error": ...}`` para que
la UI nunca se cuelgue por una excepción.

Todo corre en UN solo ``backend.run`` (los 4 circuitos CHSH juntos), así que es
compatible con IonQ (un job por ejecución).

Desde JS: ``import * as api from 'quantum.api'`` y llamar con
``.callPromisingKwargs({...})`` y luego ``.toJs()``.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any, Callable
from collections import Counter

from . import analysis as an
from . import bell, randomness
from .execute import run_batch_detailed

VERSION = "0.1.0"
ATTRIBUTION = "Qollab × IonQ Hackathon 2026."


def _guard(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            out = fn(*args, **kwargs)
            return {"ok": True, **an.to_plain(out)}
        except Exception as exc:  # noqa: BLE001 - la UI nunca debe colgarse
            msg = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"
            return {"ok": False, "error": msg}
    return wrapper


def info() -> dict[str, Any]:
    """Descripción estática para la UI: parámetros y textos."""
    return {
        "ok": True,
        "version": VERSION,
        "attribution": ATTRIBUTION,
        "title": "Quantum Dice",
        "subtitle": "Aleatoriedad certificada por una violación de Bell",
        "params": {
            "shots": {"min": 100, "max": 20000, "default": 2000},
        },
        "theory": bell.theory_chsh()["S"],
        "classical_bound": an.CLASSICAL_BOUND,
        "tsirelson": bell.TSIRELSON,
    }


def _shots(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("shots debe ser un entero") from None
    if not (100 <= n <= 20000):
        raise ValueError("shots debe estar entre 100 y 20000")
    return n


def _counts_from_memory(memory: list[str]) -> dict[str, int]:
    return dict(Counter(str(v).replace(" ", "") for v in memory))


def _split_test_generation(
    counts: dict[str, dict[str, int]], memory: dict[str, list[str]] | None
) -> tuple[dict[str, dict[str, int]], dict[str, list[str]] | None, dict[str, Any]]:
    """Divide cada ajuste en una mitad de test y reserva a0,b0 para generar.

    La primera mitad de las cuatro configuraciones forma un test CHSH
    balanceado. La segunda mitad de ``a0,b0`` genera la cadena; las otras tres
    segundas mitades no se usan. Bajo el modelo i.i.d. declarado, esto evita
    extraer de los mismos outcomes usados para estimar S. Sin memoria por shot
    no se puede separar y se deshabilita la extracción certificada.
    """
    if not memory or randomness.GEN_CIRCUIT not in memory:
        return counts, None, {
            "separated": False,
            "test_rounds_per_setting": {},
            "generation_rounds": 0,
            "reason": "sin memoria por shot",
        }
    sequence = memory[randomness.GEN_CIRCUIT]
    cut = len(sequence) // 2
    generation_sequence = sequence[cut:]
    test_counts = {}
    per_setting_test = {}
    for name, full_counts in counts.items():
        sequence_for_setting = memory.get(name)
        if sequence_for_setting:
            setting_cut = min(cut, len(sequence_for_setting))
            test_counts[name] = _counts_from_memory(sequence_for_setting[:setting_cut])
            per_setting_test[name] = setting_cut
        else:
            # No mezclar tamaños desbalanceados: si falta memoria de cualquier
            # ajuste, abandonamos el split y bloqueamos extracción.
            return counts, None, {
                "separated": False,
                "test_rounds_per_setting": {},
                "generation_rounds": 0,
                "reason": f"sin memoria para {name}",
            }
    generation_memory = {randomness.GEN_CIRCUIT: generation_sequence}
    return test_counts, generation_memory, {
        "separated": True,
        "test_rounds_per_setting": per_setting_test,
        "generation_rounds": len(generation_sequence),
        "reason": None,
    }


@_guard
def roll(backend: Any, shots: int = 2000, seed: int = 0, **run_options: Any) -> dict[str, Any]:
    """Tira el dado cuántico: corre el test CHSH y extrae aleatoriedad certificada.

    1 solo ``backend.run`` con los 4 circuitos CHSH. Devuelve S, certificación,
    bits crudos y extraídos, tiradas de dado y la viz para la UI.
    """
    if backend is None:
        raise ValueError("se requiere un backend")
    n = _shots(shots)
    circuits = bell.build_chsh()
    executed = run_batch_detailed(backend, circuits, n, **run_options)
    counts = executed["counts"]
    test_counts, generation_memory, split = _split_test_generation(counts, executed["memory"])
    decoded = bell.decode_chsh(test_counts)
    summary = randomness.summarize(
        test_counts,
        decoded,
        seed=int(seed),
        memory=generation_memory,
        use_independent_seed=True,
    )
    return {
        "backend": an.backend_name(backend),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shots": n,
        "chsh": decoded,
        **summary,
        "counts": counts,
        "test_counts": test_counts,
        "protocol": {
            "generation_test_split": split,
            "settings_schedule": "four fixed circuits; not sequential spot-checking",
            "iid_assumption": True,
        },
        "execution": {
            "memory_available": executed["memory_available"],
            "memory_requested": executed["memory_requested"],
            "memory_error": executed["memory_error"],
        },
    }
