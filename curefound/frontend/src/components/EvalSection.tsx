import { motion } from "framer-motion";

/**
 * Real numbers, taken verbatim from data/artifacts/eval_report.json.
 * Protocol: leave-one-out over the 16 TREATS triples in the seed KG;
 * for each held-out triple, all other Drug heads are filtered candidates.
 *
 * TransE baseline: same protocol, NumPy implementation.
 * RotatE (ours):   same protocol, PyTorch training -> NumPy inference.
 */
type Row = {
  metric: string;
  rotate: number;
  transe: number;
  fmt: (v: number) => string;
  delta?: string;
};

const ROWS: Row[] = [
  { metric: "MRR (filtered)", rotate: 0.380, transe: 0.131, fmt: (v) => v.toFixed(3), delta: "+190%" },
  { metric: "Hits@1",         rotate: 0.188, transe: 0.000, fmt: (v) => v.toFixed(3), delta: "first non-zero" },
  { metric: "Hits@3",         rotate: 0.375, transe: 0.062, fmt: (v) => v.toFixed(3), delta: "+506%" },
  { metric: "Hits@10",        rotate: 0.750, transe: 0.562, fmt: (v) => v.toFixed(3), delta: "+33%" },
  { metric: "Mean rank ↓",    rotate: 6.00,  transe: 9.88,  fmt: (v) => v.toFixed(2), delta: "−39%" },
];

// Per-item ranks from eval_report.json — used for the rank distribution figure.
const PER_ITEM_RANKS = [2, 4, 8, 13, 1, 15, 1, 6, 4, 4, 2, 4, 16, 2, 13, 1];

const SETUP: [string, string][] = [
  ["Model",        "RotatE — relational rotation (Sun et al., ICLR 2019)"],
  ["Embedding",    "ℂ⁶⁴ — entities ∈ ℂ^d, relations as unit-modulus rotations"],
  ["KG",           "99 nodes · 163 edges · 7 relation types"],
  ["Protocol",     "Leave-one-out over 16 TREATS triples · filtered rank"],
  ["Loss",         "Self-adversarial sigmoid · γ=6.0 · 64 negs/pos"],
  ["Optimizer",    "Adam · lr=1e-3 · 1000 epochs · batch 512"],
  ["Hardware",     "Single CPU · ~30 s per fold · 16 folds"],
];

export function EvalSection() {
  // Histogram bin counts: rank ∈ [1,5], [6,10], [11,15], [16,19]
  const bins = [
    { label: "1–5",   range: [1, 5],   count: 0 },
    { label: "6–10",  range: [6, 10],  count: 0 },
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
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-acc)]">
            02 — Eval
          </div>
          <h2 className="mt-3 font-display text-[34px] font-semibold leading-[1.1] tracking-[-0.015em] text-[var(--color-fg-0)] sm:text-[44px]">
            The numbers, no spin.
          </h2>
          <p className="mt-3 text-pretty text-[15px] text-[var(--color-fg-2)]">
            Held-out leave-one-out evaluation. Same training corpus, same protocol — RotatE
            structurally models antisymmetric relations like{" "}
            <code className="font-mono text-[var(--color-fg-1)]">TREATS</code>, where TransE
            collapses.
          </p>
          <dl className="mt-7 space-y-2.5">
            {SETUP.map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-3 border-b border-[var(--color-line)] py-1.5">
                <dt className="w-32 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                  {k}
                </dt>
                <dd className="flex-1 font-mono text-[12px] leading-snug text-[var(--color-fg-1)]">
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="flex flex-col gap-4">
          <div className="overflow-hidden rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[var(--color-line)] text-left">
                  <th className="px-5 py-3 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                    Metric
                  </th>
                  <th className="px-5 py-3 text-right font-mono text-[10px] uppercase tracking-wider text-[var(--color-acc)]">
                    RotatE (ours)
                  </th>
                  <th className="px-5 py-3 text-right font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                    TransE (baseline)
                  </th>
                  <th className="px-5 py-3 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                    Δ
                  </th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r, i) => {
                  const denom = Math.max(r.rotate, r.transe);
                  const w = denom > 0 ? r.rotate / denom : 0;
                  return (
                    <tr key={r.metric} className="border-b border-[var(--color-line)] last:border-0">
                      <td className="px-5 py-4 font-mono text-[13px] text-[var(--color-fg-0)]">{r.metric}</td>
                      <td className="px-5 py-4 text-right font-mono tabular text-[14px] text-[var(--color-fg-0)]">
                        {r.fmt(r.rotate)}
                      </td>
                      <td className="px-5 py-4 text-right font-mono tabular text-[13px] text-[var(--color-fg-2)]">
                        {r.fmt(r.transe)}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <span className="h-1.5 w-32 overflow-hidden rounded-full bg-[var(--color-bg-3)]">
                            <motion.span
                              initial={{ width: 0 }}
                              whileInView={{ width: `${Math.round(w * 100)}%` }}
                              viewport={{ once: true, margin: "-50px" }}
                              transition={{ duration: 0.6, delay: i * 0.05 }}
                              className="block h-full bg-[var(--color-acc)]"
                            />
                          </span>
                          {r.delta && (
                            <span className="font-mono tabular text-[12px] text-[var(--color-acc)]">
                              {r.delta}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Rank distribution */}
          <div className="rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                Rank distribution · n={PER_ITEM_RANKS.length}
              </span>
              <span className="font-mono text-[10px] text-[var(--color-fg-3)]">
                of {PER_ITEM_RANKS.length} held-out triples, {bins[0].count} ranked top-5
              </span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {bins.map((b, i) => (
                <div key={b.label}>
                  <div className="flex items-end gap-2">
                    <motion.div
                      initial={{ height: 0 }}
                      whileInView={{ height: `${(b.count / maxBin) * 84}px` }}
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
              KG is small (99 nodes), so absolute MRR isn&apos;t the headline — the structural
              modelling delta vs TransE is. Hits@1 going from 0 → 0.188 means RotatE actually
              gets some triples right; TransE never did.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
