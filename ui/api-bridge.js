/*
  Capa de datos: una sola API para la UI, igual en Qollab y en local.

  En Qollab el runtime inyecta `backend` (global) y permite importar módulos
  Python por su nombre con puntos ('quantum.api'); las funciones se llaman con
  `.callPromisingKwargs({...})` y el resultado se desenvuelve con `.toJs()`.

  En local no existe ninguno de los dos, así que se usa el mock (ui/mock-data.js)
  con la misma forma del contrato. main.js nunca distingue un modo del otro.
*/

import { makeMock } from "./mock-data.js";

async function detectQollab() {
  try {
    if (typeof backend === "undefined" || backend === null) return null;
    const api = await import("quantum.api");
    if (api && (api.info || api.default)) return api;
    return null;
  } catch (_err) {
    return null;
  }
}

function unwrap(value) {
  if (value && typeof value.toJs === "function") {
    return value.toJs({ dict_converter: Object.fromEntries });
  }
  return value;
}

async function callPy(fn, kwargs) {
  const result = await fn.callPromisingKwargs(kwargs);
  return unwrap(result);
}

/**
 * Crea el cliente de datos.
 *   - mode: "qollab" | "local"
 *   - backendName(): string
 *   - info(): Promise<info>
 *   - roll({shots, seed, noise}): Promise<result>  (envelope ok:true/false)
 */
export async function createClient() {
  const api = await detectQollab();

  if (api) {
    const name =
      typeof backend?.name === "function" ? backend.name() : (backend?.name ?? "qollab");
    return {
      mode: "qollab",
      backendName: () => String(name),
      async info() {
        return callPy(api.info, {});
      },
      async roll({ shots = 2000, seed = 0 } = {}) {
        // En Qollab 'noise' no aplica (el ruido lo pone el hardware/simulador).
        return callPy(api.roll, { backend, shots, seed });
      },
    };
  }

  const mock = makeMock();
  return {
    mode: "local",
    backendName: () => "local_mock",
    async info() {
      return mock.info();
    },
    async roll({ shots = 2000, seed = 0, noise = 0 } = {}) {
      return mock.roll(shots, { seed, noise });
    },
  };
}
