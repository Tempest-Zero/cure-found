import { motion } from "framer-motion";

/**
 * Real numbers, taken verbatim from data/artifacts/eval_report.json (see
 * git for the file). Protocol: leave-one-out over the 16 TREATS triples
 * in the LSD-scoped KG; for each held-out triple, all other Drug heads
 * are ranked, with other known TREATS heads for the same disease tail
 * filtered out (Sun-2019 / PyKEEN gold standard).
 *
 * Bootstrap 95% CIs come from `--bootstrap 2000` resamples in the same
 * report -- they're the headline because n=16 is small enough that point
 * estimates alone are misleading.
 *
 * R-GCN / CompGCN columns are filled in *only* if those PyKEEN-trained
 * artifacts shipped (see `scripts/colab_gnn_training.ipynb`); otherwise
 * the columns stay greyed out so the comparison story is visible without
 * pretending the run already happened.
 */
type Stat = { mean: number; lo: number; hi: number };

type ModelEval = {
  label: string;
  shipped: boolean;
  // null while we still need to run the Colab notebook
  mrr: Stat | null;
  hits1: Stat | null;
  hits3: Stat | null;
  hits10: Stat | null;
  meanRank: Stat | null;
};

const ROTATE: ModelEval = {
  label: "RotatE",
  shipped: true,
  mrr: { mean: 0.146, lo: 0.085, hi: 0.218 },
  hits1: { mean: 0.0, lo: 0.0, hi: 0.0 },
  hits3: { mean: 0.125, lo: 0.0, hi: 0.313 },
  hits10: { mean: 0.375, lo: 0.125, hi: 0.625 },
  meanRank: { mean: 10.94, lo: 8.63, hi: 13.31 },
};

// R-GCN — trained on Colab T4 (87s), eval_report_rgcn.json.
// MRR is lower than RotatE: message-passing on a small, sparse graph
// with many one-hop paths doesn't help; RotatE's rotation semantics
// encode the TREATS antisymmetry more cleanly on this KG size.
const RGCN: ModelEval = {
  label: "R-GCN",
  shipped: true,
  mrr: { mean: 0.077, lo: 0.073, hi: 0.082 },
  hits1: { mean: 0.0, lo: 0.0, hi: 0.0 },
  hits3: { mean: 0.0, lo: 0.0, hi: 0.0 },
  hits10: { mean: 0.063, lo: 0.0, hi: 0.188 },
  meanRank: { mean: 13.13, lo: 12.38, hi: 13.88 },
};

// CompGCN — Colab run timed out before completing; pending a second run.
const COMPGCN: ModelEval = {
  label: "CompGCN",
  shipped: false,
  mrr: null,
  hits1: null,
  hits3: null,
  hits10: null,
  meanRank: null,
};

const MODELS = [ROTATE, RGCN, COMPGCN];

type RowSpec = {
  metric: string;
  pick: (m: ModelEval) => Stat | null;
  fmt: (v: number) => string;
  /** Lower is better — flip the bar fill direction. */
  lowerBetter?: boolean;
};

const ROW_SPECS: RowSpec[] = [
  { metric: "MRR (filtered)", pick: (m) => m.mrr, fmt: (v) => v.toFixed(3) },
  { metric: "Hits@1", pick: (m) => m.hits1, fmt: (v) => v.toFixed(3) },
  { metric: "Hits@3", pick: (m) => m.hits3, fmt: (v) => v.toFixed(3) },
  { metric: "Hits@10", pick: (m) => m.hits10, fmt: (v) => v.toFixed(3) },
  { metric: "Mean rank", pick: (m) => m.meanRank, fmt: (v) => v.toFixed(2), lowerBetter: true },
];

// Per-item ranks from the current eval_report.json, in the same order as
// the per_item array (so the histogram matches what the JSON would render).
const PER_ITEM_RANKS = [14, 14, 17, 12, 2, 12, 15, 17, 15, 14, 9, 2, 8, 7, 4, 13];

// The three reviewer-flagged "honest failures" — kept as a callout so the
// page stays credible. Numbers from per_item entries on the current report.
const KNOWN_FAILURES: { drug: string; disease: string; rank: string; note: string }[] = [
  {
    drug: "Arimoclomol",
    disease: "Niemann-Pick C",
    rank: "12 / 17",
    note: "HSP-co-inducer mechanism is unrepresented in the KG — model has no signal to lean on.",
  },
  {
    drug: "N-acetyl-L-leucine",
    disease: "Niemann-Pick C",
    rank: "8 / 17",
    note: "Improved from previous KG (was rank 14) thanks to HPO phenotype overlap with Miglustat.",
  },
  {
    drug: "Tetrabenazine",
    disease: "Huntington",
    rank: "4 / 19",
    note: "VMAT2-mediated symptomatic treatment now in the top-5 — HD lacks lysosomal pathway depth.",
  },
];

const SETUP: [string, string][] = [
  ["KG", "673 nodes · 1,057 edges · 7 relation types · 13 LSDs + HD + CF"],
  ["Phenotype layer", "894 HAS_PHENOTYPE edges from HPOA (real curated data)"],
  ["Protocol", "Leave-one-out · filtered rank · n=16 TREATS triples"],
  ["Bootstrap", "Non-parametric resample · 2,000 iters · 95% CI"],
  ["RotatE", "ℂ⁶⁴ · γ=6.0 · self-adv. sigmoid · 64 negs · Adam 1e-3 · 300 epochs"],
  ["GNN baselines", "R-GCN + CompGCN via PyKEEN · DistMult head · same protocol"],
  ["Inference", "Pure NumPy at runtime — no PyTorch in the production container"],
];

function fmtCi(s: Stat | null, fmt: (v: number) => string): string {
  if (!s) return "—";
  return `[${fmt(s.lo)}, ${fmt(s.hi)}]`;
}

export function EvalSection() {
  // Histogram bins: rank ∈ [1,5], [6,10], [11,15], [16,19].
  const bins = [
    { label: "1–5", range: [1, 5], count: 0 },
    { label: "6–10", range: [6, 10], count: 0 },
    { label: "11–15", range: [11, 15], count: 0 },
    { label: "16–19", range: [16, 19], count: 0 },
  ];
  for (const r of PER_ITEM_RANKS) {
    for (const b of bins) {
      if (r >= b.range[0] && r <= b.range[1]) {
        b.count++;
        break;
      }
    }
  }
  const maxBin = Math.max(...bins.map((b) => b.count));

  return (
    <section id="eval" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      <div className="grid gap-10 lg:grid-cols-[420px_1fr]">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="font-mono uppercase tracking-[0.18em] text-[var(--color-acc)]" style={{ fontSize: 'var(--fs-eyebrow)' }}>
            02 — Eval
          </div>
          <h2 className="mt-3 font-display font-semibold leading-[1.1] tracking-[-0.015em] text-[var(--color-fg-0)]" style={{ fontSize: 'var(--fs-h2)' }}>
            The numbers, with confidence intervals.
          </h2>
          <p className="mt-3 text-pretty text-[var(--color-fg-2)]" style={{ fontSize: 'var(--fs-body)' }}>
            Held-out leave-one-out over 16 TREATS triples on the LSD-scoped KG. n is small,
            so the bootstrap 95% CI is the honest headline — and it&apos;s wide on purpose.
            R-GCN and CompGCN share the same protocol; their columns light up the moment the
            T4-trained artifacts ship into the deploy.
          </p>
          <dl className="mt-7 space-y-2.5">
            {SETUP.map(([k, v]) => (
              <div
                key={k}
                className="flex items-baseline gap-3 border-b border-[var(--color-line)] py-1.5"
              >
                <dt className="w-32 shrink-0 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                  {k}
                </dt>
                <dd className="flex-1 font-mono text-[12px] leading-snug text-[var(--color-fg-1)]">
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </motion.div>

        <div className="flex flex-col gap-4">
          {/* ----- Three-model comparison table with CIs ----- */}
          <div className="tilt overflow-hidden rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[var(--color-line)] text-left">
                  <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                    Metric
                  </th>
                  {MODELS.map((m) => (
                    <th
                      key={m.label}
                      className={
                        "px-4 py-3 text-right font-mono text-[10px] uppercase tracking-wider " +
                        (m.shipped ? "text-[var(--color-acc)]" : "text-[var(--color-fg-3)]/60")
                      }
                    >
                      {m.label}
                      {!m.shipped && (
                        <span className="ml-1 text-[8px] normal-case tracking-normal opacity-70">
                          (pending)
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROW_SPECS.map((row, i) => {
                  // Bar widths are normalized to the largest *shipped* value in the row.
                  const shippedVals = MODELS.filter((m) => m.shipped)
                    .map((m) => row.pick(m)?.mean)
                    .filter((v): v is number => typeof v === "number");
                  const maxVal = shippedVals.length > 0 ? Math.max(...shippedVals) : 1;

                  return (
                    <tr
                      key={row.metric}
                      className="border-b border-[var(--color-line)] last:border-0"
                    >
                      <td className="px-4 py-4 font-mono text-[13px] text-[var(--color-fg-0)]">
                        {row.metric}
                        {row.lowerBetter && (
                          <span className="ml-1 text-[10px] text-[var(--color-fg-3)]">↓</span>
                        )}
                      </td>
                      {MODELS.map((m) => {
                        const stat = row.pick(m);
                        const w =
                          stat && maxVal > 0 ? Math.min(1, (stat.mean ?? 0) / maxVal) : 0;
                        return (
                          <td
                            key={m.label}
                            className={
                              "px-4 py-4 text-right " +
                              (m.shipped ? "" : "text-[var(--color-fg-3)]/50")
                            }
                          >
                            <div className="flex flex-col items-end gap-1">
                              <span className="font-mono tabular text-[14px] text-[var(--color-fg-0)]">
                                {stat ? row.fmt(stat.mean) : "—"}
                              </span>
                              <span className="font-mono text-[10px] text-[var(--color-fg-3)]">
                                {fmtCi(stat, row.fmt)}
                              </span>
                              {m.shipped && stat && (
                                <span className="block h-1 w-20 overflow-hidden rounded-full bg-[var(--color-bg-3)]">
                                  <motion.span
                                    initial={{ width: 0 }}
                                    whileInView={{ width: `${Math.round(w * 100)}%` }}
                                    viewport={{ once: true, margin: "-50px" }}
                                    transition={{ duration: 0.6, delay: i * 0.05 }}
                                    className="block h-full bg-[var(--color-acc)]"
                                  />
                                </span>
                              )}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* ----- Rank distribution ----- */}
          <div className="tilt rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                Rank distribution · RotatE · n={PER_ITEM_RANKS.length}
              </span>
              <span className="font-mono text-[10px] text-[var(--color-fg-3)]">
                {bins[0].count}/{PER_ITEM_RANKS.length} held-out triples ranked top-5
              </span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {bins.map((b, i) => (
                <div key={b.label}>
                  <div className="flex items-end gap-2">
                    <motion.div
                      initial={{ height: 0 }}
                      whileInView={{ height: `${(b.count / Math.max(maxBin, 1)) * 84}px` }}
                      viewport={{ once: true, margin: "-50px" }}
                      transition={{ duration: 0.6, delay: i * 0.06 }}
                      className={
                        i === 0
                          ? "w-full rounded-t-md bg-[var(--color-acc)]"
                          : "w-full rounded-t-md bg-[var(--color-fg-3)]/40"
                      }
                    />
                  </div>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="font-mono text-[10px] text-[var(--color-fg-3)]">{b.label}</span>
                    <span className="font-mono tabular text-[12px] text-[var(--color-fg-1)]">
                      {b.count}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 font-mono text-[10px] leading-relaxed text-[var(--color-fg-3)]">
              The KG is small (673 nodes, 16 LOO folds), so absolute MRR isn&apos;t the
              headline — the GNN-vs-RotatE delta is. Per-fold ranks come straight from
              <code className="mx-1 font-mono text-[var(--color-fg-2)]">eval_report.json</code>;
              re-run via{" "}
              <code className="font-mono text-[var(--color-fg-2)]">
                python -m app.ml.eval --bootstrap 2000
              </code>
              .
            </p>
          </div>

          {/* ----- Known-failure callout ----- */}
          <div className="tilt rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                Honest failures · reviewer-flagged
              </span>
              <span className="font-mono text-[10px] text-[var(--color-fg-3)]">RotatE</span>
            </div>
            <ul className="divide-y divide-[var(--color-line)]">
              {KNOWN_FAILURES.map((f) => (
                <li key={f.drug + f.disease} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 py-3">
                  <span className="font-mono text-[13px] text-[var(--color-fg-0)]">
                    {f.drug}{" "}
                    <span className="text-[var(--color-fg-3)]">→</span>{" "}
                    <span className="text-[var(--color-fg-1)]">{f.disease}</span>
                  </span>
                  <span className="font-mono tabular text-[12px] text-[var(--color-fg-1)]">
                    rank {f.rank}
                  </span>
                  <span className="col-span-2 font-mono text-[10px] leading-relaxed text-[var(--color-fg-3)]">
                    {f.note}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
