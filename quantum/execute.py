"""Ejecución en UN solo backend.run (obligatorio en IonQ: un job por run).

Además de histogramas, ``run_batch_detailed`` solicita memoria por shot cuando
el backend la soporta. Esa memoria es imprescindible para extraer una cadena de
bits: un histograma agregado no conserva la secuencia original y no debe
presentarse como si fuera la salida cruda certificada.
"""

from __future__ import annotations

import re
from typing import Any

from qiskit import QuantumCircuit, transpile
from qiskit.transpiler.passes import RemoveBarriers

from . import analysis as an

IONQ_BASIS = ["h", "x", "y", "z", "s", "sdg", "rx", "ry", "rz", "cx"]
Counts = dict[str, int]


def compile_for(backend: Any, circuits: list[QuantumCircuit], seed: int = 1234) -> list[QuantumCircuit]:
    if an.is_ionq(backend):
        stripped = [RemoveBarriers()(qc) for qc in circuits]
        try:
            return transpile(stripped, basis_gates=IONQ_BASIS, optimization_level=1, seed_transpiler=seed)
        except Exception:  # noqa: BLE001
            return stripped
    try:
        return transpile(circuits, backend=backend, optimization_level=1, seed_transpiler=seed)
    except Exception:  # noqa: BLE001
        return circuits


def _validate(circuits: list[QuantumCircuit]) -> list[str]:
    names = [qc.name for qc in circuits]
    if len(set(names)) != len(names):
        raise ValueError("circuit names must be unique")
    for qc in circuits:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", qc.name):
            raise ValueError(f"unsafe circuit name {qc.name!r}")
        assert len(qc.cregs) == 1, f"{qc.name}: expected a single classical register"
    return names


def _memory_guaranteed(backend: Any) -> bool:
    """Si podemos pedir memoria sin arriesgar un job IonQ.

    Qollab/IonQ garantiza histogramas, no memoria por shot en todas las rutas.
    Como IonQ permite un solo job, no podemos probar y reintentar: allí usamos
    el modo histograma y declaramos extracción no disponible. Simuladores
    locales de Qiskit sí admiten ``memory=True``.
    """
    return not an.is_ionq(backend)


def run_batch_detailed(
    backend: Any,
    circuits: list[QuantumCircuit],
    shots: int = 2000,
    seed: int = 1234,
    request_memory: bool = True,
    **run_options: Any,
) -> dict[str, Any]:
    """Ejecuta el lote una sola vez y devuelve counts + memoria por shot.

    ``memory`` es ``None`` cuando el proveedor no la garantiza. No se reintenta
    después del job (regla de un solo job en IonQ).
    """
    names = _validate(circuits)
    compiled = compile_for(backend, circuits, seed)
    ask_memory = bool(request_memory and _memory_guaranteed(backend))
    opts = dict(run_options)
    if ask_memory:
        opts["memory"] = True
    result = backend.run(compiled, shots=shots, **opts).result()
    counts = {name: dict(result.get_counts(i)) for i, name in enumerate(names)}
    memory: dict[str, list[str]] | None = None
    memory_error = None
    if ask_memory:
        try:
            memory = {name: [str(v).replace(" ", "") for v in result.get_memory(i)] for i, name in enumerate(names)}
        except Exception as exc:  # noqa: BLE001 - counts siguen siendo útiles
            memory_error = f"{type(exc).__name__}: {exc}"
            memory = None
    return {
        "counts": counts,
        "memory": memory,
        "memory_available": memory is not None,
        "memory_requested": ask_memory,
        "memory_error": memory_error,
    }


def run_batch(
    backend: Any, circuits: list[QuantumCircuit], shots: int = 2000, seed: int = 1234, **run_options: Any
) -> dict[str, Counts]:
    """Compatibilidad: devuelve solo counts, pero mantiene un único job."""
    return run_batch_detailed(
        backend, circuits, shots, seed, request_memory=False, **run_options
    )["counts"]
