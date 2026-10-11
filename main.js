/*
  Quantum Dice — orquestador de la UI.

  Flujo: createClient() (Qollab real o mock local) -> info() -> escena 3D del
  dado -> botón "Tirar" llama roll() -> anima el dado, actualiza el medidor de
  S, el veredicto (viola Bell o no) y muestra la certificación y los bits.

  Idéntico en local y en Qollab (la diferencia vive en ui/api-bridge.js).
*/

import { createClient } from "./ui/api-bridge.js";
import { DiceScene } from "./ui/scene.js";

const els = {
  scene: document.getElementById("scene-container"),
  loader: document.getElementById("loader"),
  shots: document.getElementById("shots"),
  shotsValue: document.getElementById("shots-value"),
  noise: document.getElementById("noise"),
  noiseValue: document.getElementById("noise-value"),
  noiseField: document.getElementById("noise-field"),
  rollBtn: document.getElementById("roll-btn"),
  runStatus: document.getElementById("run-status"),
  results: document.getElementById("results"),
  backendBadge: document.getElementById("backend-badge"),
  meterFill: document.getElementById("meter-fill"),
  sValue: document.getElementById("s-value"),
  sCi: document.getElementById("s-ci"),
  verdict: document.getElementById("verdict"),
};

let client;
let scene;
let info;

async function boot() {
  client = await createClient();
  els.backendBadge.textContent = `backend: ${client.backendName()}`;
  // El ruido solo tiene sentido en el mock local.
  if (client.mode !== "local") els.noiseField.style.display = "none";

  info = await client.info();

  scene = new DiceScene(els.scene);

  els.shots.addEventListener("input", () => (els.shotsValue.textContent = els.shots.value));
  els.noise.addEventListener("input", () => (els.noiseValue.textContent = (+els.noise.value).toFixed(2)));
  els.rollBtn.addEventListener("click", roll);

  requestAnimationFrame(() => setTimeout(() => els.loader.classList.add("hidden"), 300));

  window.__QDICE__ = {
    mode: client.mode,
    roll,
    get last() {
      return lastResult;
    },
  };
}

let lastResult = null;

async function roll() {
  setBusy(true);
  try {
    const shots = parseInt(els.shots.value, 10);
    const noise = parseFloat(els.noise.value) || 0;
    const result = await client.roll({ shots, seed: Date.now() & 0xffff, noise });
    lastResult = result;

    if (!result || result.ok === false) {
      renderError(result?.error ?? "error desconocido");
      return;
    }

    // Elegir la cara del dado desde los bits (primera tirada si hay).
    const face = result.dice_rolls?.[0] ?? 1;
    const violates = result.viz?.finite_certificate ?? result.certification?.extractable ?? false;

    // Actualizar medidor y veredicto antes de la animación.
    updateMeter(result);

    await scene.roll(face, violates);
    renderResult(result);
  } catch (err) {
    renderError(String(err?.message ?? err));
  } finally {
    setBusy(false);
  }
}

// --- Medidor de S ---------------------------------------------------------
function updateMeter(result) {
  const S = result.chsh?.S ?? result.viz?.S ?? 0;
  const tsirelson = result.viz?.tsirelson ?? 2 * Math.SQRT2;
  const ci = result.chsh?.S_ci95 ?? result.viz?.S_ci95;
  // La escala va de 0 a Tsirelson; el 2 (clásico) cae en 2/2.83 = 70.7%.
  const pct = Math.max(0, Math.min(1, S / tsirelson)) * 100;
  els.meterFill.style.width = `${pct}%`;
  const finiteCertificate = result.viz?.finite_certificate ?? result.certification?.extractable ?? false;
  els.meterFill.classList.toggle("meter__fill--quantum", finiteCertificate);
  els.meterFill.classList.toggle("meter__fill--warn", !finiteCertificate);

  els.sValue.textContent = S.toFixed(3);
  els.sCi.textContent = ci ? `IC95 [${ci[0].toFixed(2)}, ${ci[1].toFixed(2)}]` : "";

  if (finiteCertificate) {
    els.verdict.className = "verdict verdict--ok";
    els.verdict.innerHTML = "✓ Cota finita supera Bell — salida <b>extraíble bajo el modelo i.i.d.</b>";
  } else {
    els.verdict.className = "verdict verdict--warn";
    const blockers = result.certification?.blockers?.join("; ");
    els.verdict.innerHTML = `⚠ Sin salida certificada${blockers ? `: ${blockers}` : ": la cota conservadora no supera 2"}`;
  }
}

// --- Resultados -----------------------------------------------------------
function card(name, value, detail) {
  return `<div class="metric"><div class="metric__name">${name}</div>` +
    `<div class="metric__value">${value}</div>` +
    (detail ? `<div class="metric__detail">${detail}</div>` : "") + `</div>`;
}

function renderResult(r) {
  const cert = r.certification || {};
  const sig = r.viz?.significance_sigma ?? r.chsh?.significance_sigma;
  const rolls = (r.dice_rolls || []).map((d) => `🎲${d}`).join(" ");
  const hRaw = r.raw_bits?.bias;
  const hExt = r.extracted_bits?.bias;
  const eat = r.eat_readiness || r.viz?.eat_readiness;
  const eps = cert.eps_total;

  let html = "";
  html += card("Salida finita extraíble", cert.certified_bits ?? 0,
    `${(cert.h_min_per_round ?? 0).toFixed(3)} bits/ronda · ${cert.rounds ?? 0} rondas de generación`);
  html += card("Corrección estadística de Bell",
    `${(cert.S_observed ?? r.chsh?.S ?? 0).toFixed(3)} → ${(cert.S_lower ?? 2).toFixed(3)}`,
    `S observado → cota unilateral; ${cert.test_rounds ?? 0} rondas de test`);
  html += card("Tasas de entropía",
    `${(cert.h_min_per_round ?? 0).toFixed(3)} / ${(cert.h_vn_first_order_rate ?? 0).toFixed(3)}`,
    "min-entropía finita i.i.d. / tasa von Neumann de primer orden");
  html += card("Error total ε",
    eps != null ? Number(eps).toExponential(1) : "—",
    `ε estimación ${(cert.eps_est ?? 0).toExponential?.(1) ?? "—"} + ε extractor ${(cert.eps_ext ?? 0).toExponential?.(1) ?? "—"}`);
  html += card("Penalización de tamaño finito",
    `${Math.round(cert.finite_size_penalty_bits ?? 0)} bits`,
    "entropía que no contamos por incertidumbre estadística");
  html += card("Significancia observada", sig != null ? `${sig.toFixed(1)}σ` : "—",
    "visualización; la salida usa la cota de Hoeffding más conservadora");
  if (rolls) html += card("Tiradas del dado", rolls, "generadas solo con la salida Toeplitz extraída");
  if (hRaw != null && hExt != null) {
    html += card("Sesgo de los bits",
      `${(hRaw * 100).toFixed(1)}% → ${(hExt * 100).toFixed(1)}%`,
      "crudo → extraído (más cerca de 0% = más uniforme)");
  }
  if (r.extracted_bits?.hex) {
    html += `<div class="metric"><div class="metric__name">Bits extraídos (hex)</div>` +
      `<div class="bits-hex">${r.extracted_bits.hex}</div></div>`;
  }
  if (eat && !eat.ready) {
    html += card("Auditoría EAT", "No se reclama EAT",
      `Falta: ${(eat.missing || []).join(" · ")}`);
  }

  html += `<p class="disclosure">Garantía componible dentro del modelo declarado:
    rondas i.i.d., memoria por shot, split test/generación y semilla Toeplitz
    pública independiente. No se afirma device-independence/EAT porque Qollab
    ejecuta cuatro circuitos con ajustes fijos, no spot-checking secuencial.</p>`;

  els.results.innerHTML = html;
}

function renderError(msg) {
  els.results.innerHTML = `<div class="results__error">Error: ${msg}</div>`;
  els.verdict.className = "verdict";
  els.verdict.textContent = "";
}

function setBusy(busy) {
  els.rollBtn.disabled = busy;
  els.runStatus.textContent = busy ? "midiendo…" : "";
}

boot().catch((err) => {
  els.loader?.classList.add("hidden");
  els.results.innerHTML = `<div class="results__error">Fallo al iniciar: ${err?.message ?? err}</div>`;
  console.error(err);
});
