# Quantum Dice — Documento de obra (qué se construyó y cómo)

Resumen técnico de todo lo implementado en el proyecto **Quantum Dice**
(aleatoriedad certificada por una violación de Bell/CHSH), para el hackathon
Qollab × IonQ 2026. Este documento describe cada archivo, la matemática, las
decisiones de honestidad científica y cómo se verificó.

Ubicación: `/home/pablo/Projects/quantum/quantum_dice`

---

## 1. Qué es el proyecto

Un generador de números aleatorios donde la impredecibilidad **no se asume: se
mide**. Preparamos pares de Bell |Φ⁺⟩, jugamos el test CHSH, y a partir de la
violación de Bell (valor S > 2) calculamos **cuántos bits de aleatoriedad
genuina** podemos extraer frente a un adversario con información lateral
cuántica, con un error total ε explícito.

Narrativa para jueces: "un dado que nadie puede amañar, y aquí está la prueba
matemática". Casos de uso: sorteos/loterías auditables, claves, muestreo
imparcial, votaciones.

Corre entero en el navegador (Qollab/Pyodide): física en Qiskit (un solo
`backend.run`, requisito de IonQ) + web en JS. En local la web usa un *mock*
con la misma forma del contrato.

---

## 2. Estructura de archivos

```
quantum_dice/
├── index.html             # Web (proyecto JS en Qollab). Import map three.js.
├── main.css               # Estilos: tema dado naranja / cuántico turquesa.
├── main.js                # Orquestador de la UI (188 líneas).
├── README.md              # Concepto + matemática + honestidad.
├── MATH_HANDOFF.md         # Brief que se usó para la parte matemática.
├── PROJECT_OVERVIEW.md     # Este documento.
├── pyproject.toml          # Config del paquete Python + pytest.
├── requirements.txt        # qiskit, numpy (igual que el runtime de Qollab).
├── .gitignore
├── quantum/                # La física y la matemática (backend).
│   ├── __init__.py
│   ├── analysis.py        # Estadística y utilidades (140 líneas).
│   ├── bell.py            # Circuitos CHSH + decodificación de S (132).
│   ├── certify.py         # NÚCLEO matemático de certificación (304).
│   ├── execute.py         # Un solo backend.run + memoria por shot (102).
│   ├── randomness.py      # Extracción de bits + extractor Toeplitz (307).
│   └── api.py             # Fachada JS-facing (159).
├── tests/
│   ├── test_bell.py       # 9 tests de física CHSH.
│   └── test_certify.py    # 8 tests de certificación/extractor.
└── ui/
    ├── api-bridge.js      # Capa de datos Qollab/local (74).
    ├── mock-data.js       # Mock local, espejo del contrato (216).
    └── scene.js           # Escena 3D del dado (three.js, 286).
```

Total: ~2.100 líneas de código propio. 17 tests, todos en verde.

---

## 3. El backend (física + matemática)

### 3.1 `quantum/bell.py` — el test CHSH
- Prepara |Φ⁺⟩ = (|00⟩+|11⟩)/√2 y lo mide en 4 combinaciones de ángulos:
  Alice {0, π/2}, Bob {π/4, −π/4}.
- `build_chsh()` → 4 circuitos (`chsh_a0_b0`, `_a0_b1`, `_a1_b0`, `_a1_b1`),
  pensados para salir en **un solo** `backend.run`.
- `S = E00 + E01 + E10 − E11`. Ideal (Tsirelson) = 2√2 ≈ 2.828; límite clásico
  = 2.
- `decode_chsh()` calcula S con IC95 (Agresti-Coull), significancia en σ, y
  además el **conteo de victorias del juego CHSH** (`wins`, `rounds`,
  `win_rate`), que es lo que alimenta la cota finita.

### 3.2 `quantum/certify.py` — el corazón matemático (lo nuevo y potente)
Reemplaza por completo el "margen de seguridad del 10%" heurístico que había
antes. Implementa:

- `guessing_probability(S)` y `h_min_local(S)`: min-entropía local de un bit de
  Alice certificada por S:
  `H_min(A|E) = −log₂[(1 + √(2 − S²/4))/2]`. Vale 0 en S=2 y 1 en Tsirelson.
- `h_vn(S)`: entropía condicional de von Neumann por ronda,
  `H(A|E) ≥ 1 − h₂((1 + √((S/2)²−1))/2)`. Es la tasa de primer orden que usan
  las pruebas EAT.
- `min_tradeoff(S0)`: construye una función afín que acota `h_vn` por debajo en
  toda la región (verificado como minorante global en los tests). Punto de
  entrada para una futura prueba EAT.
- `chsh_lower_bound(S_hat, n_test, eps_est)`: **cota unilateral de Hoeffding**
  sobre el score verdadero del juego:
  `ω ≥ ω̂ − √(ln(1/ε_est)/(2·N_test))`, de donde sale un **S conservador** `S_L`.
- `extractor_output_length(k, eps_ext)`: longitud de salida por el **quantum
  leftover hash lemma**: `ℓ = ⌊k − 2·log₂(1/ε_ext)⌋`.
- `certify_iid(...)`: pipeline finito completo. Devuelve bits certificados,
  tasas, ε_total = ε_est + ε_ext, penalización de tamaño finito, y una lista de
  **blockers** explícitos (si falta memoria por shot o semilla independiente,
  los bits certificados se fijan en 0).
- `eat_readiness(...)`: **auditoría honesta**. Reporta `eat_claimed = False`
  porque el protocolo actual no cumple los requisitos de una prueba EAT
  (ver §5).

### 3.3 `quantum/randomness.py` — de la física a los bits
- `shot_memory_bits(memory, ...)`: extrae la cadena **real por shot** desde
  `Result.get_memory` (little-endian). Esta es la fuente válida de bits.
- `raw_bits(counts, ...)`: serialización de un histograma; marcada como **solo
  diagnóstico** (un histograma NO reconstruye la secuencia cuántica; no se usa
  para extraer salida certificada).
- `toeplitz_extract(bits, out_len, seed_bits=...)`: extractor Toeplitz
  2-universal sobre GF(2), acelerado con **FFT** (≈ O(n log n)), verificado bit
  a bit contra una multiplicación directa.
- `independent_seed_bits(length)`: semilla pública independiente desde el
  CSPRNG del runtime (`secrets`).
- `certified_bits(...)`: delega en `certify.certify_iid` (sin margen heurístico;
  `security_margin` queda como `None`).
- `summarize(...)`: arma el contrato JSON para la UI; **solo extrae bits si hay
  memoria por shot y semilla independiente**, si no, muestra el presupuesto
  pero 0 bits certificados.

### 3.4 `quantum/execute.py` — ejecución
- `run_batch_detailed(...)`: corre los 4 circuitos en **un solo** `backend.run`
  y pide **memoria por shot** cuando el backend la soporta (simuladores locales
  sí; IonQ no se arriesga por la regla de un job). Devuelve counts + memoria +
  flags.
- `run_batch(...)`: wrapper de compatibilidad (solo counts).

### 3.5 `quantum/analysis.py` — estadística
- Parseo de counts a bits (little-endian), paridad, correladores, intervalo de
  Wilson, varianza Agresti-Coull, helpers JSON. `CLASSICAL_BOUND = 2.0`.

### 3.6 `quantum/api.py` — fachada JS-facing
- `info()` y `roll(backend, shots, seed)`, con envelope `{ok: ...}` que nunca
  lanza excepción (la UI no se cuelga).
- **Separación test/generación**: la primera mitad de cada ajuste forma un test
  CHSH balanceado; la segunda mitad de `a0,b0` genera la cadena. Así no se
  extrae de los mismos outcomes usados para estimar S.
- Expone `protocol`, `execution` (memoria disponible o no) y el certificado.

---

## 4. La web (frontend)

- `index.html`: proyecto JS de Qollab (index.html + main.js en la raíz). three.js
  por import map (CDN); sin assets binarios → portable al iframe sandbox.
- `ui/scene.js` (three.js): dado 3D que gira en "superposición" y **colapsa** al
  tirar; dos partículas entrelazadas (Alice/Bob) salen de la fuente; aura
  turquesa = certificado; bloom + tone mapping ACES. Pips nítidos.
- `ui/api-bridge.js`: detecta Qollab (usa `quantum.api` real vía
  `callPromisingKwargs().toJs()`) o local (mock). `main.js` es idéntico en ambos.
- `ui/mock-data.js`: mock local con **la misma matemática** (cota de Hoeffding,
  leftover hash, split test/generación, auditoría EAT).
- `main.js`: tirar → medidor de S → tarjetas del certificado. El veredicto se
  basa en el **certificado finito** (no solo en S > 2).
- UI muestra: S observado → S conservador, min-entropía / von Neumann, ε total,
  penalización de tamaño finito, bits extraídos (hex), tiradas de dado y la
  auditoría EAT.

---

## 5. Decisiones de honestidad científica (lo que te distingue)

Durante la implementación matemática se detectaron dos cosas que un enfoque
"espectacular pero incorrecto" habría ocultado. Se corrigieron:

1. **No se reclama una prueba EAT/device-independent completa.** El protocolo
   corre 4 circuitos con ajustes fijos y conocidos; una prueba EAT necesita
   spot-checking secuencial con ajustes aleatorios elegidos justo antes de cada
   ronda, y entradas desconocidas por el dispositivo. El certificado reporta
   `eat_claimed = false` y una lista de lo que falta (`eat_readiness`). Sí se
   calcula la tasa de von Neumann de primer orden y la min-tradeoff function,
   dejando el camino preparado.

2. **Un histograma no es una cadena de bits.** `counts` pierde el orden por
   shot; expandirlo no reconstruye la secuencia cuántica. Por eso la extracción
   certificada **requiere memoria por shot** (`get_memory`). Si el backend no la
   da, se muestra el test de Bell y el presupuesto de entropía, pero la
   extracción se marca como no disponible (es lo correcto, no un fallo).

La garantía que SÍ se afirma: **componible dentro del modelo i.i.d. declarado**
(rondas i.i.d., memoria por shot, split test/generación, semilla Toeplitz
pública independiente), con ε_total = ε_est + ε_ext.

---

## 6. La fórmula central (resumen)

```
ω_L  = ω̂ − √( ln(1/ε_est) / (2·N_test) )        (Hoeffding, cota inferior de S)
S_L  = 8·ω_L − 4
H_min(A|E) = −log₂( (1 + √(2 − S_L²/4)) / 2 )     (min-entropía local certificada)
ℓ    = ⌊ n_gen · H_min(A|E) − 2·log₂(1/ε_ext) ⌋   (leftover hash lemma)
ε_total ≤ ε_est + ε_ext
```

Ya no existe el margen heurístico del 10%.

---

## 7. Verificación realizada

- **Tests Python**: 17 pasan (`.venv/bin/python -m pytest -q`).
  - `test_bell.py` (9): CHSH ≈ 2.83 y viola con >3σ en `BasicSimulator`;
    min-entropía monótona con bordes 0/1; API `ok` + JSON + dados 1–6.
  - `test_certify.py` (8): bordes y monotonía de h_min y h_vn; Hoeffding
    conservador y mejora con N; leftover hash exacto; bloqueo sin memoria o sin
    semilla; auditoría EAT honesta; **Toeplitz FFT = multiplicación GF(2)
    directa**; min-tradeoff minorante global.
- **Sintaxis JS**: `node --check` OK en `main.js`, `ui/scene.js`,
  `ui/api-bridge.js`, `ui/mock-data.js`.
- **Navegador headless (Chromium)**: 0 errores de página/consola. Ejemplo real:
  S = 2.828 → S_L = 2.496, ~224 bits (mock), ε = 2e-6, EAT = false, 10 tarjetas.
- **Tirada real con Qiskit** (`BasicSimulator`, 2000 shots): memoria por shot
  disponible, S ≈ 2.878 → S_L ≈ 2.546, 1000 rondas de generación, ~267 bits
  certificados, semilla pública independiente, ε = 2e-6.

---

## 8. Cómo ejecutar en local

**Web:**
```bash
cd /home/pablo/Projects/quantum/quantum_dice
python3 -m http.server 8124
# abrir http://localhost:8124  (badge: local_mock)
```

**Tests de física/matemática:**
```bash
.venv/bin/python -m pytest -q      # 17 passed
```

**Tirada real con Qiskit:**
```bash
.venv/bin/python -c "
from qiskit.providers.basic_provider import BasicSimulator
from quantum import api
r = api.roll(BasicSimulator(), 2000, seed_simulator=7)
print('S', round(r['chsh']['S'],3), '-> S_L', round(r['certification']['S_lower'],3))
print('bits', r['certification']['certified_bits'], 'eps', r['certification']['eps_total'])
print('memoria por shot:', r['execution']['memory_available'])
"
```

---

## 9. Qué falta (siguiente paso)

- **Validar en Qollab con un simulador real**: confirmar que el puente real
  funciona y, sobre todo, **si el backend devuelve memoria por shot** (de eso
  depende la extracción certificada). Es el único hueco pendiente.
- Opcional: subir a git (repo nuevo recomendado), features extra (comparación
  clásico vs cuántico, exportar bits, tests estadísticos en vivo).

---

## 10. Referencias (citadas en el código)

- CHSH: Clauser, Horne, Shimony & Holt, *PRL* 23, 880 (1969).
- Aleatoriedad certificada por Bell: Pironio et al., *Nature* 464, 1021 (2010).
- Seguridad DI y acumulación de entropía: Arnon-Friedman, Renner & Vidick
  (arXiv:1607.01797); Dupuis, Fawzi & Renner (arXiv:1607.01796).
- Quantum leftover hashing: Tomamichel, Schaffner, Smith & Renner
  (arXiv:1002.2436).
- Cota de Tsirelson (S ≤ 2√2): Tsirelson, *Lett. Math. Phys.* 4, 93 (1980).
