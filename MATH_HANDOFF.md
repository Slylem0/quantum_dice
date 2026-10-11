# MATH HANDOFF — El núcleo matemático de alto impacto de Quantum Dice

> Para el modelo potente. Objetivo: elevar el proyecto de "demo que certifica
> aleatoriedad con una fórmula de juguete" a **"protocolo de expansión de
> aleatoriedad con seguridad componible y una cota ajustada de tasa de bits,
> derivada por Acumulación de Entropía (EAT)"**. Esto es lo que impresiona a un
> jurado técnico: es el estado del arte real (Arnon-Friedman et al., *Nature
> Communications* 2018), casi nunca implementado en un hackathon.

---

## 0. Resumen ejecutivo (qué vas a construir)

Implementar, en Python puro + NumPy (debe correr en Pyodide/Qollab, sin SciPy
si se puede evitar; si usas SciPy, que sea opcional con fallback), un módulo

    quantum/certify.py

que, dado el resultado de un lote de rondas CHSH (ya lo produce el backend),
calcule **la cantidad de aleatoriedad verdadera, componible y a prueba de
adversario cuántico**, con TRES ingredientes que hoy NO existen en el proyecto:

1. **min-tradeoff function f(S)** y la **cota de von Neumann** h(S): la tasa de
   entropía por ronda como función del valor CHSH, derivada correctamente
   (no la fórmula provisional actual).
2. **Entropy Accumulation Theorem (EAT)**: convierte la tasa asintótica h(S) en
   una **cota de min-entropy total para n rondas finitas** con un parámetro de
   seguridad epsilon_s componible, incluyendo el término de corrección de
   tamaño finito O(sqrt(n)).
3. **Extractor componible** (Toeplitz / leftover hash) con el número de bits de
   salida FIJADO por la cota EAT y un epsilon_ext explícito, de modo que el
   epsilon total del protocolo sea epsilon_s + epsilon_ext (seguridad
   componible real, no un "margen" heurístico).

El entregable estrella es una **fórmula única y defendible**:

    bits_seguros(n, S, eps) = n * h(S) - sqrt(n) * Delta(eps, ...) - 2*log2(1/eps_ext)

y su implementación verificada. Hoy el proyecto usa
`H_min * n * (1 - 0.1)` con un 0.1 inventado: eso es exactamente lo que hay que
reemplazar por algo riguroso.

---

## 1. Contexto del código actual (interfaces reales que debes respetar)

- `quantum/bell.py`:
  - `build_chsh()` -> 4 circuitos CHSH (`chsh_a0_b0`, `_a0_b1`, `_a1_b0`,
    `_a1_b1`), un solo job. Ángulos Alice {0, pi/2}, Bob {pi/4, -pi/4}.
    Ideal S = 2*sqrt(2). Límite clásico 2.
  - `decode_chsh(counts_by_id) -> dict` con claves:
    `S`, `S_ci95`, `sigma`, `significance_sigma`, `correlators`, `theory`,
    `violates`. **No cambies estas firmas**; puedes añadir campos.
- `quantum/randomness.py`:
  - `min_entropy_from_S(S) -> float`  ← PROVISIONAL, a reemplazar/mejorar.
  - `certified_bits(n_rounds, S, security_margin=0.1) -> dict` con claves
    `h_min_per_round`, `rounds`, `total_min_entropy`, `security_margin`,
    `certified_bits`.  ← El `security_margin` heurístico es lo que EAT elimina.
  - `toeplitz_extract(bits, out_len, seed=0) -> list[int]`  ← ya multiplica en
    GF(2); hay que fijar `out_len` desde la cota, no a dedo.
  - `summarize(counts, decoded, seed) -> dict` arma el payload de la UI.
- Convención de bits: little-endian Qiskit; clbit 0 = Alice, 1 = Bob.
- Entorno de pruebas: `.venv/bin/python -m pytest -q` (hoy 9 tests en verde).

**Restricción dura:** todo debe seguir corriendo en Pyodide (Qollab). Python +
NumPy sí. SciPy: evítalo o hazlo opcional. Nada que requiera compilación nativa
fuera de lo que ya trae Qiskit/NumPy.

---

## 2. Pieza 1 — Cota de entropía por ronda h(S)  (von Neumann / DI)

### 2.1 Qué hay que derivar
La tasa de aleatoriedad certificable **frente a un adversario cuántico** (no
solo clásico) para una sola parte (p. ej. el bit de Alice en el ajuste de
generación), condicionada al valor CHSH observado S, es la cota conocida:

    H(A | E)  >=  1 - h2( 1/2 + 1/2 * sqrt( (S/2)^2 - 1 ) )          (★)

donde `h2` es la entropía binaria. Esta es la curva de Pironio/Masanes para la
entropía condicional de **un bit** en el escenario CHSH (válida para
2 <= S <= 2*sqrt(2); da 0 en S=2 y 1 en S=2*sqrt(2)).

Tareas:
1. **Implementar `h_vn(S)` = (★)** con cuidado numérico en los bordes
   (clipping del argumento a [0,1], devolver 0 bajo S=2).
2. **Comparar y documentar** la diferencia con la fórmula provisional actual
   `-log2(1/2 + 1/2 sqrt(2 - S^2/4))`. Explicar en un comentario cuál es la
   correcta para "entropía condicional contra adversario cuántico" (★) frente a
   la de "probabilidad de adivinanza local". Elegir (★) como cota principal y
   justificar con cita (Pironio et al. 2010; Masanes-Pironio-Acín 2011).
3. **Opcional (nota de impacto):** mencionar que la cota apretada moderna se
   obtiene por optimización SDP (Navascués-Pironio-Acín / jerarquía NPA). NO
   hace falta implementar el SDP (no cabe en Pyodide), pero deja la función
   escrita de forma que `h_vn` pueda sustituirse por una tabla NPA si algún día
   se precomputa. Documenta esto.

### 2.2 Firma propuesta
```python
def h_vn(S: float) -> float:
    """Entropía condicional H(A|E) por ronda (bits) certificada por CHSH=S,
    frente a un adversario cuántico. Fórmula (★). 0 si S<=2, 1 en Tsirelson."""
```

---

## 3. Pieza 2 — Entropy Accumulation (el corazón, lo "brutal")

### 3.1 Idea
Con n rondas, la min-entropy total NO es simplemente n*h(S): hay una corrección
de tamaño finito. El **EAT** (Dupuis-Fawzi-Renner; Arnon-Friedman et al. 2018)
da una cota de la forma:

    H_min^{eps_s}(A_1..A_n | E)  >=  n * h(S_obs)  -  n * (algo que ->0)
                                 ≈   n * f(p_obs)  -  c * sqrt(n)             (†)

donde:
- `f` es una **min-tradeoff function**: una función afín que acota por debajo la
  tasa de von Neumann alrededor del valor observado (su derivada controla el
  término sqrt(n)).
- `c` depende de: el parámetro de seguridad `eps_s`, la varianza / la pendiente
  máxima de `f` (Var(f) o max-min de f), la dimensión del alfabeto de salida, y
  `log(1/eps_s)`.

### 3.2 Qué implementar
1. **`min_tradeoff(S0)`**: construir la función afín f tangente (o secante
   conservadora) a `h_vn` en el punto de trabajo `S0` (el S esperado/observado).
   Devolver sus coeficientes y la cota de su derivada.
2. **`eat_lower_bound(n, S_obs, eps_s, ...) -> dict`**: implementar (†) con el
   término de corrección explícito. Usa la forma estándar del EAT para
   protocolos i.i.d.-friendly:

       H_min^{eps_s} >= n*h(S_obs) - sqrt(n) * sqrt(2*log(2/eps_s^2)) * (max_grad)
                        - correcciones de orden log(n)

   Debes fijar la constante concreta citando la versión del teorema que uses
   (recomendado: la formulación "second-order" / EAT con min-tradeoff de
   Dupuis-Fawzi 2019 o Liu et al.; o, si prefieres algo más simple y
   defendible, una cota tipo Azuma-Hoeffding sobre el estimador de S + la
   relación entropía/adivinanza, dejando claro que es una cota válida aunque no
   la óptima EAT). **Lo importante: que sea correcta y citada, no máxima.**
3. Devolver un dict con: `h_rate` (= h_vn(S_obs)), `finite_size_penalty`
   (el término sqrt(n)), `smooth_min_entropy_total`, `eps_s`, y
   `bits_before_extraction`.

### 3.3 Firmas propuestas
```python
def min_tradeoff(S0: float) -> dict:
    """Coeficientes de la min-tradeoff function afín alrededor de S0, y su
    pendiente máxima (para el término sqrt(n) del EAT)."""

def eat_lower_bound(n: int, S_obs: float, eps_s: float = 1e-6) -> dict:
    """Cota de smooth-min-entropy total H_min^{eps_s}(A^n|E) por EAT.
    Devuelve h_rate, finite_size_penalty, smooth_min_entropy_total,
    eps_s, bits_before_extraction. Debe ->0 cuando S_obs->2 y ser
    monótona creciente en (S_obs, n)."""
```

---

## 4. Pieza 3 — Extracción componible (leftover hash) con epsilon explícito

Reemplazar el `security_margin` heurístico por la cuenta correcta del **Leftover
Hash Lemma** con un extractor Toeplitz (2-universal):

    out_len = floor( H_min^{eps_s}_total  -  2*log2(1/eps_ext)  )            (‡)

y el epsilon total del protocolo es `eps_total = eps_s + eps_ext`.

Tareas:
1. **`extractor_output_length(smooth_min_entropy_total, eps_ext=1e-6) -> int`**
   usando (‡), con floor y clamp a >= 0.
2. Ajustar `toeplitz_extract` para que el `out_len` provenga de (‡) y DOCUMENTAR
   que la semilla Toeplitz debe ser aleatoriedad pública independiente (hoy es
   un PRNG; para la demo está bien, pero dilo en el docstring y en la UI).
3. Exponer `eps_total` en el resultado.

---

## 5. Integración (cómo se conecta con lo existente)

Crear `quantum/certify.py` con `h_vn`, `min_tradeoff`, `eat_lower_bound`,
`extractor_output_length` y una función de orquestación:

```python
def certify(n_rounds: int, S_obs: float, eps_s: float = 1e-6,
            eps_ext: float = 1e-6) -> dict:
    """Pipeline completo: h_vn -> EAT -> leftover hash. Devuelve:
       h_rate, finite_size_penalty, smooth_min_entropy_total,
       certified_bits, eps_s, eps_ext, eps_total, y un 'explanation' corto."""
```

Luego, en `quantum/randomness.py`:
- Reescribir `certified_bits(n_rounds, S, ...)` para que **delegue en**
  `certify(...)` (manteniendo las claves de salida actuales + añadiendo
  `eps_total`, `finite_size_penalty`, `h_rate`), para no romper `summarize` ni
  la UI.
- `summarize` debe pasar a la `viz` los nuevos campos (`eps_total`,
  `finite_size_penalty`, `h_rate`) para que la UI los muestre (yo me encargo de
  la UI una vez existan).

**No toques** `bell.py` (la física está bien) ni la forma del contrato que
consume el frontend; solo añade campos.

---

## 6. Criterios de aceptación (tests que deben pasar)

Añade/ajusta `tests/test_certify.py`. Deben cumplirse:

1. **Bordes de h_vn:** `h_vn(2.0) == 0` y `h_vn(2*sqrt(2)) == 1` (abs 1e-9);
   monótona creciente en [2, 2sqrt2].
2. **EAT < asintótico:** para todo n finito,
   `eat_lower_bound(n, S)["smooth_min_entropy_total"] < n * h_vn(S)`
   (la corrección de tamaño finito resta), y la brecha -> 0 relativo cuando
   n -> infinito (p. ej. ratio a n*h_vn tiende a 1 al crecer n).
3. **Monotonía:** más rondas y mayor S nunca dan menos bits certificados.
4. **Extracción componible:** `extractor_output_length(k, eps)` =
   floor(k - 2log2(1/eps)); nunca negativo; `eps_total = eps_s + eps_ext`.
5. **No regresión:** los 9 tests actuales (`tests/test_bell.py`) siguen en verde.
   Si cambias los bordes de `min_entropy_from_S`, actualiza su test explicando
   el porqué en el commit/comentario.
6. **Determinismo y JSON:** `certify(...)` devuelve tipos JSON planos
   (sin numpy), serializable con `json.dumps`.

Comando: `.venv/bin/python -m pytest -q`

---

## 7. Qué NO hacer (límites de honestidad del proyecto)

- No afirmar que es un dispositivo **device-independent** con los loopholes
  cerrados: el hardware/simulador de Qollab no los cierra. El README ya es
  honesto; mantén ese tono. La seguridad es **componible bajo el modelo i.i.d.
  / supuestos declarados**, con EAT dando el puente a tamaño finito.
- No metas un SDP/NPA pesado que no corra en Pyodide. Deja `h_vn` como función
  analítica (★), con un hook documentado por si se precomputa una tabla NPA.
- No cambies las firmas públicas que usa el frontend sin añadir, nunca quitar.

---

## 8. Material de referencia (citar en docstrings)

- Pironio, Acín, Massanes, et al. (2010). *Random numbers certified by Bell's
  theorem*. Nature 464, 1021. (cota de entropía vs S)
- Masanes, Pironio, Acín (2011). *Secure device-independent randomness...*
  Nat. Commun. 2, 238.
- Dupuis, Fawzi, Renner (2020). *Entropy Accumulation*. Commun. Math. Phys. 379.
- Arnon-Friedman, Dupuis, Fawzi, Renner, Vidick (2018). *Practical
  device-independent randomness amplification/expansion*. Nat. Commun. 9, 459.
- Dupuis & Fawzi (2019). *Entropy accumulation with improved second-order term*.
- Tomamichel, Schaffner, Smith, Renner (2011). *Leftover hashing against quantum
  side information*. IEEE Trans. Inf. Theory 57.
- Tsirelson (1980). Lett. Math. Phys. 4, 93. (S <= 2sqrt2)

---

## 9. Entregable final esperado

- `quantum/certify.py` con las 4-5 funciones y `certify()`.
- `quantum/randomness.py` ajustado para delegar en `certify()` (sin romper UI).
- `tests/test_certify.py` con los criterios de §6, todo en verde junto a los 9
  tests existentes.
- Docstrings con las fórmulas (★), (†), (‡) y las citas.
- Un párrafo en el README explicando, en lenguaje de jurado, por qué
  "Entropy Accumulation + leftover hashing" es seguridad componible real y no un
  margen inventado. (Ese párrafo es parte del oro de la presentación.)
