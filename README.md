# Quantum Dice — aleatoriedad certificada por física

Un dado que **nadie puede amañar** — y lo demostramos con mecánica cuántica.

> Hecho para el Qollab × IonQ Global Quantum Hackathon 2026.

## La idea en una frase

La mayoría de los generadores de números aleatorios te piden *confiar* en el
aparato. Aquí medimos una violación de Bell y la convertimos en una cota
cuantitativa de impredecibilidad. Dentro del modelo declarado —rondas i.i.d.,
memoria por shot, separación test/generación y semilla independiente— obtenemos
una cantidad explícita de bits extraíbles frente a información lateral
cuántica, junto con su error total ε.

Casos de uso: sorteos y loterías auditables, claves criptográficas, muestreo
estadístico imparcial, votaciones.

## Cómo funciona (resumen)

1. Preparamos pares de Bell (|Φ⁺⟩) y los medimos en 4 combinaciones de ángulos
   (el test CHSH). Todo en **un solo** `backend.run` (requisito de IonQ).
2. Estimamos el valor **S** (CHSH). Para |Φ⁺⟩ ideal, S = 2√2 ≈ 2.83; el límite
   clásico es 2.
3. Separamos datos: la primera mitad de cada ajuste estima CHSH; la segunda
   mitad de `a0,b0` genera la cadena. Una cota unilateral de Hoeffding produce
   un **S conservador** `S_L` con fallo `ε_est`.
4. De `S_L` derivamos la min-entropía local por ronda:

   `H_min(A|E) = -log₂[(1 + √(2-S_L²/4))/2]`.

5. El quantum leftover-hash lemma fija la salida Toeplitz sin márgenes
   inventados:

   `ℓ = floor(n_gen·H_min(A|E) - 2log₂(1/ε_ext))`,

   con error total `ε_total ≤ ε_est + ε_ext`.
6. La UI muestra S observado, S conservador, penalización finita, ε total,
   bits extraídos y las tiradas.

## Honestidad sobre los supuestos (importante)

La aleatoriedad **device-independent** completa exige cerrar los *loopholes* de
localidad y detección y elegir ajustes aleatorios justo antes de cada medida.
Qollab ejecuta cuatro circuitos con ajustes fijos y algunos proveedores solo
devuelven histogramas. Por eso el proyecto expone dos límites en el propio
certificado:

- La garantía finita implementada es componible **dentro del modelo i.i.d.
  declarado**, cuando el backend devuelve memoria por shot y el extractor usa
  una semilla pública independiente.
- No afirmamos una prueba EAT/device-independent completa. El resultado incluye
  una auditoría `eat_readiness` con los requisitos que faltan: spot-checking
  secuencial y entradas desconocidas por el dispositivo.

Esta distinción evita presentar una penalización heurística como seguridad
formal. `quantum/certify.py` también calcula la tasa de von Neumann de primer
orden y una min-tradeoff function, dejando preparada la evolución hacia EAT.

## Cómo ejecutar

- **En Qollab:** abre el proyecto, elige un simulador o QPU en "Select QPU" y
  pulsa **Run**.
- **Localmente (desarrollo de la web):** `python3 -m http.server` y abre el
  navegador; la UI usa un *mock* con la misma forma del contrato del backend.
- **Tests de la física:** `uv run pytest` (o `pytest`).

## Referencias

- CHSH: Clauser, Horne, Shimony & Holt, *Phys. Rev. Lett.* 23, 880 (1969).
- Aleatoriedad certificada por Bell: [Pironio et al., Nature 464, 1021 (2010)](https://doi.org/10.1038/nature09008).
- Seguridad DI y acumulación: [Arnon-Friedman, Renner & Vidick](https://arxiv.org/abs/1607.01797).
- Quantum leftover hashing: [Tomamichel et al.](https://arxiv.org/abs/1002.2436).
- Entropy Accumulation: [Dupuis, Fawzi & Renner](https://arxiv.org/abs/1607.01796).
- Cota de Tsirelson (S ≤ 2√2): Tsirelson, *Lett. Math. Phys.* 4, 93 (1980).

## Licencia

MIT.
