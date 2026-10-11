/*
  Mock del backend para desarrollo local de la UI.

  Reproduce la forma del contrato JSON de quantum/api.py (info, roll) SIN correr
  Qiskit, con números plausibles derivados de las mismas fórmulas de la física
  (CHSH ideal ~2.83, min-entropy de S, extracción). En Qollab se usa el backend
  real y este archivo se ignora.
*/

const TSIRELSON = 2 * Math.SQRT2;
const CLASSICAL_BOUND = 2.0;

function makeRng(seed = 1) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

// Espejo de quantum/certify.py: cota finita i.i.d. explícita.
function minEntropyFromS(S) {
  S = Math.max(CLASSICAL_BOUND, Math.min(S, TSIRELSON));
  const inside = Math.max(0, 2 - (S * S) / 4);
  const pGuess = Math.min(1, Math.max(0.5, 0.5 + 0.5 * Math.sqrt(inside)));
  return -Math.log2(pGuess);
}

function binaryEntropy(p) {
  p = Math.max(0, Math.min(1, p));
  if (p === 0 || p === 1) return 0;
  return -p * Math.log2(p) - (1 - p) * Math.log2(1 - p);
}

function hVn(S) {
  S = Math.max(CLASSICAL_BOUND, Math.min(S, TSIRELSON));
  const q = 0.5 * (1 + Math.sqrt(Math.max(0, (S / 2) ** 2 - 1)));
  return Math.max(0, Math.min(1, 1 - binaryEntropy(q)));
}

function certifiedBits(nGeneration, S, nTest, epsEst = 1e-6, epsExt = 1e-6) {
  const omegaHat = Math.max(0, Math.min(1, (S + 4) / 8));
  const delta = Math.sqrt(Math.log(1 / epsEst) / (2 * nTest));
  const omegaLower = Math.max(0, omegaHat - delta);
  const sLowerRaw = 8 * omegaLower - 4;
  const sLower = Math.max(CLASSICAL_BOUND, Math.min(TSIRELSON, sLowerRaw));
  const certifies = sLowerRaw > CLASSICAL_BOUND;
  const h = certifies ? minEntropyFromS(sLower) : 0;
  const total = h * nGeneration;
  const budget = Math.max(0, Math.floor(total - 2 * Math.log2(1 / epsExt)));
  return {
    framework: "finite_iid_chsh_local_min_entropy",
    security_model: "i.i.d. rounds + finite Hoeffding parameter estimation + quantum-proof leftover hashing",
    composable_within_stated_model: true,
    eat_claimed: false,
    h_min_per_round: h,
    h_vn_first_order_rate: certifies ? hVn(sLower) : 0,
    rounds: nGeneration,
    test_rounds: nTest,
    total_min_entropy: total,
    extractor_budget_bits: budget,
    certified_bits: budget,
    extractable: budget > 0,
    blockers: budget > 0 ? [] : ["la cota finita no deja entropía extraíble"],
    eps_est: epsEst,
    eps_ext: epsExt,
    eps_total: epsEst + epsExt,
    S_observed: S,
    S_lower: sLower,
    S_lower_raw: sLowerRaw,
    omega_hat: omegaHat,
    omega_lower: omegaLower,
    finite_size_penalty_bits: Math.max(0, nGeneration * minEntropyFromS(S) - total),
    extractor_seed_independent: true,
    per_shot_memory: true,
    security_margin: null,
    explanation: budget > 0
      ? "Salida certificada dentro del modelo i.i.d. declarado."
      : "La muestra es insuficiente para una salida finita con estos epsilons.",
  };
}

function bitsToHex(bits) {
  if (!bits.length) return "";
  let s = bits.join("");
  s = s + "0".repeat((4 - (s.length % 4)) % 4);
  let hex = "";
  for (let i = 0; i < s.length; i += 4) hex += parseInt(s.slice(i, i + 4), 2).toString(16);
  return hex;
}

function diceRolls(bits, n = 5) {
  const rolls = [];
  let i = 0;
  while (rolls.length < n && i + 3 <= bits.length) {
    const v = (bits[i] << 2) | (bits[i + 1] << 1) | bits[i + 2];
    i += 3;
    if (v < 6) rolls.push(v + 1);
  }
  return rolls;
}

export function makeMock() {
  let seed = 1;
  return {
    info() {
      return {
        ok: true,
        version: "0.1.0-mock",
        attribution: "Qollab × IonQ Hackathon 2026.",
        title: "Quantum Dice",
        subtitle: "Aleatoriedad certificada por una violación de Bell",
        params: { shots: { min: 100, max: 20000, default: 2000 } },
        theory: TSIRELSON,
        classical_bound: CLASSICAL_BOUND,
        tsirelson: TSIRELSON,
      };
    },
    async roll(shots = 2000, { seed: s = 0, noise = 0 } = {}) {
      await new Promise((r) => setTimeout(r, 350));
      const rng = makeRng(seed++ + (s | 0));
      // S cercano a Tsirelson con un poco de ruido/jitter (noise ∈ [0,1] lo baja).
      const sIdeal = TSIRELSON * (1 - 0.4 * noise);
      const S = Math.max(1.9, Math.min(TSIRELSON, sIdeal + (rng() - 0.5) * 0.08));
      const sigma = 0.03;
      const shotsPerCircuit = Math.floor(shots);
      // Igual que la API real: primera mitad de cada ajuste para test CHSH;
      // segunda mitad de a0,b0 para generación.
      const nGeneration = shotsPerCircuit - Math.floor(shotsPerCircuit / 2);
      const nTest = 4 * Math.floor(shotsPerCircuit / 2);

      const raw = Array.from({ length: Math.min(nGeneration, 10000) }, () => (rng() < 0.5 ? 0 : 1));
      const cert = certifiedBits(nGeneration, S, nTest);
      const nOut = Math.min(cert.certified_bits, raw.length);
      const extracted = Array.from({ length: nOut }, () => (rng() < 0.5 ? 0 : 1));
      const p1raw = raw.reduce((a, b) => a + b, 0) / (raw.length || 1);
      const p1ext = extracted.length ? extracted.reduce((a, b) => a + b, 0) / extracted.length : 0;
      const rolls = diceRolls(extracted);

      const half = 1.96 * sigma;
      const violates = S - half > CLASSICAL_BOUND;
      return {
        ok: true,
        backend: "local_mock",
        timestamp: new Date().toISOString(),
        shots: shotsPerCircuit,
        chsh: {
          S,
          S_ci95: [S - half, S + half],
          sigma,
          significance_sigma: (S - CLASSICAL_BOUND) / sigma,
          violates,
          game: {
            rounds: nTest,
            win_rate: (S + 4) / 8,
            S_from_win_rate: S,
          },
          theory: { S: TSIRELSON, tsirelson: TSIRELSON, classical_bound: CLASSICAL_BOUND },
        },
        certification: cert,
        raw_bits: {
          n: raw.length, available: true, p1: p1raw,
          bias: Math.abs(p1raw - 0.5), hex: bitsToHex(raw.slice(0, 256)),
        },
        extracted_bits: {
          n: extracted.length,
          p1: extracted.length ? p1ext : null,
          bias: extracted.length ? Math.abs(p1ext - 0.5) : null,
          hex: bitsToHex(extracted.slice(0, 256)),
          seed_source: "mock_public_independent",
        },
        dice_rolls: rolls,
        protocol: {
          generation_test_split: {
            separated: true,
            test_rounds_per_setting: Object.fromEntries(
              ["chsh_a0_b0", "chsh_a0_b1", "chsh_a1_b0", "chsh_a1_b1"].map((k) => [k, nTest / 4])
            ),
            generation_rounds: nGeneration,
          },
          settings_schedule: "four fixed circuits; not sequential spot-checking",
          iid_assumption: true,
        },
        execution: { memory_available: true, memory_requested: true, memory_error: null },
        eat_readiness: {
          ready: false,
          missing: ["ajustes CHSH aleatorios por ronda", "entradas elegidas después de iniciar cada ronda"],
          note: "No se reclama seguridad EAT: el lote actual no implementa spot-checking secuencial.",
        },
        viz: {
          S,
          S_ci95: [S - half, S + half],
          S_lower: cert.S_lower,
          classical_bound: CLASSICAL_BOUND,
          tsirelson: TSIRELSON,
          violates,
          finite_certificate: cert.extractable,
          significance_sigma: (S - CLASSICAL_BOUND) / sigma,
          h_min_per_round: cert.h_min_per_round,
          h_vn_first_order_rate: cert.h_vn_first_order_rate,
          eps_total: cert.eps_total,
          finite_size_penalty_bits: cert.finite_size_penalty_bits,
          raw_bias: Math.abs(p1raw - 0.5),
          extracted_bias: extracted.length ? Math.abs(p1ext - 0.5) : null,
          rolls,
          raw_preview: raw.slice(0, 64),
          extracted_preview: extracted.slice(0, 64),
          eat_readiness: {
            ready: false,
            missing: ["ajustes CHSH aleatorios por ronda", "entradas elegidas después de iniciar cada ronda"],
          },
        },
      };
    },
  };
}
