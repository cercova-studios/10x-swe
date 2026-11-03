// Threshold tuning and calibration check for saved decision-model scores.
//
// Input JSON: [{"model": str, "id": str, "score": float, "label": 0|1}, ...]
// Run with --self-check to verify the logic on synthetic data.
// Requires Node >= 22.18 (type stripping on by default); no dependencies.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

type Row = { model: string; id: string; score: number; label: number };
type Opts = { folds: number; seed: number; beta: number; minPrecision: number; minRecall: number };
type Metrics = [precision: number, recall: number, fbeta: number];

export function metrics(y: number[], s: number[], t: number, beta: number): Metrics {
  let tp = 0, fp = 0, fn = 0;
  for (let i = 0; i < y.length; i++) {
    const pred = s[i] >= t;
    if (pred && y[i] === 1) tp++;
    else if (pred) fp++;
    else if (y[i] === 1) fn++;
  }
  const p = tp + fp ? tp / (tp + fp) : 0;
  const r = tp + fn ? tp / (tp + fn) : 0;
  const b2 = beta * beta;
  return [p, r, b2 * p + r ? ((1 + b2) * p * r) / (b2 * p + r) : 0];
}

/** Best F-beta threshold meeting both floors; null if no threshold qualifies. */
export function pickThreshold(y: number[], s: number[], o: Opts): number | null {
  let best: [number, number] | null = null;
  for (const t of [...new Set(s)].sort((a, b) => a - b)) {
    const [p, r, f] = metrics(y, s, t, o.beta);
    if (p >= o.minPrecision && r >= o.minRecall && (best === null || f > best[1])) best = [t, f];
  }
  return best && best[0];
}

const logit = (v: number) => {
  const c = Math.min(Math.max(v, 1e-6), 1 - 1e-6);
  return Math.log(c / (1 - c));
};
const sigmoid = (z: number) => 1 / (1 + Math.exp(-z));

/** Platt fit p = sigmoid(a*logit(s) + b) by Newton's method. L2 penalty 0.5*a^2
 * on the slope only, matching scikit-learn's LogisticRegression() default (C=1). */
export function fitPlatt(y: number[], s: number[]): (v: number) => number {
  const x = s.map(logit);
  let a = 0, b = 0;
  for (let it = 0; it < 100; it++) {
    let ga = a, gb = 0, haa = 1, hab = 0, hbb = 0;
    for (let i = 0; i < x.length; i++) {
      const p = sigmoid(a * x[i] + b), w = p * (1 - p), e = p - y[i];
      ga += e * x[i]; gb += e;
      haa += w * x[i] * x[i]; hab += w * x[i]; hbb += w;
    }
    const det = haa * hbb - hab * hab || 1e-12;
    const da = (hbb * ga - hab * gb) / det, db = (haa * gb - hab * ga) / det;
    a -= da; b -= db;
    if (Math.abs(da) + Math.abs(db) < 1e-10) break;
  }
  return (v) => sigmoid(a * logit(v) + b);
}

export const brier = (y: number[], p: number[]) =>
  y.reduce((acc, yi, i) => acc + (p[i] - yi) ** 2, 0) / y.length;

/** Deterministic stratified k-fold: shuffle each class with a seeded PRNG, deal round-robin. */
export function stratifiedFolds(y: number[], k: number, seed: number): number[][] {
  let state = seed >>> 0;
  const rand = () => { // mulberry32
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 2 ** 32;
  };
  const folds: number[][] = Array.from({ length: k }, () => []);
  let next = 0;
  for (const cls of [0, 1]) {
    const idx = y.flatMap((v, i) => (v === cls ? [i] : []));
    for (let i = idx.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [idx[i], idx[j]] = [idx[j], idx[i]];
    }
    for (const i of idx) folds[next++ % k].push(i);
  }
  return folds;
}

const meanStd = (v: number[]) => {
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length);
  return `${m.toFixed(3)} ± ${sd.toFixed(3)}`;
};

export function evaluate(y: number[], s: number[], o: Opts) {
  const pick = <T>(arr: T[], idx: number[]) => idx.map((i) => arr[i]);
  const rows: number[][] = [];
  const platt = new Array<number>(y.length).fill(0);
  let infeasible = 0;
  const folds = stratifiedFolds(y, o.folds, o.seed);
  for (const va of folds) {
    const held = new Set(va);
    const tr = y.map((_, i) => i).filter((i) => !held.has(i));
    const t = pickThreshold(pick(y, tr), pick(s, tr), o);
    if (t === null) { // report, never relax the floors
      infeasible++;
      continue;
    }
    rows.push([...metrics(pick(y, va), pick(s, va), t, o.beta), t]);
    const cal = fitPlatt(pick(y, tr), pick(s, tr));
    for (const i of va) platt[i] = cal(s[i]);
  }
  const [precision, recall, fbeta] = metrics(y, s, 0.5, o.beta);
  const out: Record<string, unknown> = {
    "default_0.50": { precision, recall, fbeta },
    infeasible_folds: `${infeasible}/${o.folds}`,
    brier_raw: brier(y, s),
  };
  if (rows.length) {
    out.tuned_cv = Object.fromEntries(
      ["precision", "recall", "fbeta", "threshold"].map((k, i) => [k, meanStd(rows.map((r) => r[i]))]),
    );
  }
  if (infeasible === 0) out.brier_platt = brier(y, platt); // Platt preds cover every trace only when all folds ran
  return out;
}

function assert(cond: boolean, msg: unknown): asserts cond {
  if (!cond) throw new Error(`self-check failed: ${JSON.stringify(msg)}`);
}

function selfCheck() {
  let state = 1;
  const rand = () => ((state = (state * 48271) % 2147483647) / 2147483647);
  const y = [...Array(60).fill(1), ...Array(40).fill(0)];
  const s = y.map((v) => (v ? 0.3 + 0.2 * rand() : 0.2 * rand()));
  const o: Opts = { folds: 5, seed: 0, beta: 1, minPrecision: 0.8, minRecall: 0.8 };
  const r = evaluate(y, s, o) as any;
  assert(r["default_0.50"].recall === 0, r); // default misses everything
  assert(parseFloat(r.tuned_cv.fbeta) > 0.95, r); // tuned ~separates; CV gap allowed
  assert(r.infeasible_folds === "0/5", r);
  assert(evaluate(y, s, { ...o, minPrecision: 1.01 }).infeasible_folds === "5/5", "impossible floor");
  console.log("self-check ok");
}

function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      "min-precision": { type: "string", default: "0" },
      "min-recall": { type: "string", default: "0" },
      beta: { type: "string", default: "1" },
      folds: { type: "string", default: "5" },
      seed: { type: "string", default: "0" },
      "self-check": { type: "boolean", default: false },
    },
  });
  if (values["self-check"]) return selfCheck();
  if (!positionals[0]) {
    console.error("usage: node tune.ts SCORES.json [--min-precision P] [--min-recall R] [--beta B] [--folds K] [--seed N] | --self-check");
    process.exit(2);
  }
  const o: Opts = {
    folds: Number(values.folds), seed: Number(values.seed), beta: Number(values.beta),
    minPrecision: Number(values["min-precision"]), minRecall: Number(values["min-recall"]),
  };
  const byModel = new Map<string, { y: number[]; s: number[] }>();
  for (const r of JSON.parse(readFileSync(positionals[0], "utf8")) as Row[]) {
    const m = byModel.get(r.model) ?? { y: [], s: [] };
    m.y.push(r.label); m.s.push(Number(r.score));
    byModel.set(r.model, m);
  }
  const report = Object.fromEntries([...byModel].map(([m, d]) => [m, evaluate(d.y, d.s, o)]));
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
