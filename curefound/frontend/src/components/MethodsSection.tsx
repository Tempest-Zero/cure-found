import { CircuitBoard, Layers, Network, Sigma, Workflow } from "lucide-react";

const PIPELINE = [
  {
    icon: Network,
    title: "Curated KG",
    body: "13 rare diseases, 19 drugs, 13 genes, 16 proteins, 12 pathways, 26 symptoms — joined by 7 typed relations: TREATS, TARGETS, CAUSES, ENCODES, HAS_PHENOTYPE, PARTICIPATES_IN, ASSOCIATED_WITH.",
  },
  {
    icon: Layers,
    title: "Leave-one-out eval",
    body: "16 TREATS triples, each held out in turn. Filtered rank: all other Drug heads compete; previously-seen TREATS edges for the same disease are excluded. Honest, no train-test bleed.",
  },
  {
    icon: Sigma,
    title: "RotatE — ℂ⁶⁴",
    body: "Entities are 64-dim complex vectors. Each relation is a unit-modulus rotation r = e^(iθ). Score = −‖h ∘ r − t‖₂. Self-adversarial sigmoid loss, γ=6.0, 64 negs/pos. Models antisymmetric TREATS structurally.",
  },
  {
    icon: CircuitBoard,
    title: "Hybrid fusion",
    body: "Two rankings — RotatE model_score and Jaccard pathway-neighborhood overlap (graph_score) — combined with Reciprocal Rank Fusion (k=60). Approved drugs filtered before ranking by default.",
  },
  {
    icon: Workflow,
    title: "Evidence path",
    body: "Every prediction ships with a 1–3-hop path drug→protein→pathway→disease pulled from the KG. The reviewer can read why the model picked each candidate — no black box.",
  },
];

export function MethodsSection() {
  return (
    <section id="methods" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      <div className="max-w-[760px]">
        <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-acc)]">
          05 — Methods
        </div>
        <h2 className="mt-3 font-display text-[34px] font-semibold leading-[1.1] tracking-[-0.015em] text-[var(--color-fg-0)] sm:text-[44px]">
          How it works, end to end.
        </h2>
        <p className="mt-3 text-pretty text-[15px] text-[var(--color-fg-2)]">
          Knowledge graph embedding + graph heuristic + traceable provenance. Every prediction
          can be opened and read.
        </p>
      </div>

      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map((s, i) => (
          <div
            key={s.title}
            className="rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] tabular text-[var(--color-fg-3)]">
                0{i + 1}
              </span>
              <s.icon size={15} className="text-[var(--color-acc)]" />
            </div>
            <div className="mt-3 font-display text-[16px] font-semibold text-[var(--color-fg-0)]">
              {s.title}
            </div>
            <p className="mt-1.5 text-[12.5px] leading-[1.55] text-[var(--color-fg-2)]">{s.body}</p>
          </div>
        ))}
      </div>

      {/* Equation strip */}
      <div className="mt-6 overflow-x-auto rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5">
        <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          model
        </div>
        <div className="mt-2 font-mono text-[14px] text-[var(--color-fg-0)] sm:text-[16px]">
          score(h, r, t) = −‖h ∘ e<sup>iθ_r</sup> − t‖<sub>2</sub> &nbsp;
          <span className="text-[var(--color-fg-3)]">where h, t ∈ ℂ⁶⁴, |e<sup>iθ_r</sup>| = 1</span>
        </div>
        <div className="mt-4 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          loss
        </div>
        <div className="mt-2 font-mono text-[13px] leading-relaxed text-[var(--color-fg-1)] sm:text-[14px]">
          ℒ = −log σ(γ − d<sub>pos</sub>) − Σ<sub>j</sub> p(neg<sub>j</sub>) · log σ(d<sub>neg<sub>j</sub></sub> − γ)
          <div className="mt-1 font-mono text-[11px] text-[var(--color-fg-3)]">
            Self-adversarial sampling: harder negatives weighted higher via a softmax over their
            distances (temperature α=0.5).
          </div>
        </div>
        <div className="mt-4 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          fused rank
        </div>
        <div className="mt-2 font-mono text-[14px] text-[var(--color-fg-0)] sm:text-[15px]">
          RRF(d) = 1/(60 + rank<sub>model</sub>(d)) + 1/(60 + rank<sub>graph</sub>(d))
        </div>
      </div>
    </section>
  );
}
