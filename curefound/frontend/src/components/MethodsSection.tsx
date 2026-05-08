import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { CircuitBoard, Layers, Network, Sigma, Workflow } from "lucide-react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { ease, spring, scrub, gsapEase, varCard, varSectionHead, varBadge, orchCards } from "@/lib/motion";

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
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!gridRef.current) return;
    const ctx = gsap.context(() => {
      const cards = gsap.utils.toArray<HTMLElement>(".method-card");
      cards.forEach((card, i) => {
        // Scroll-in with inertia lag — each card slightly offset for organic feel
        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: card,
            start: "top 78%",
            end: "top 42%",
            scrub: scrub.normal + i * 0.06,
          },
        });
        tl.fromTo(
          card,
          { y: 18, scale: 0.97, opacity: 0.7 },
          {
            y: 0,
            scale: 1,
            opacity: 1,
            ease: gsapEase.snap,
          },
        );

        // Active zone: card glows as it passes the viewport sweet-spot
        gsap.to(card, {
          scrollTrigger: {
            trigger: card,
            start: "top 55%",
            end: "top 20%",
            scrub: scrub.tight,
          },
          borderColor: "color-mix(in oklab, var(--color-line) 35%, var(--color-acc) 65%)",
          boxShadow: "0 20px 48px -20px rgba(94,227,139,.32), 0 0 0 1px rgba(94,227,139,.1)",
          ease: gsapEase.scrub,
        });
      });
    }, gridRef);
    return () => ctx.revert();
  }, []);

  return (
    <section id="methods" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      {/* Section header — orchestrated: eyebrow snaps, heading lands heavy */}
      <motion.div
        variants={{
          hidden: {},
          show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
        }}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        className="max-w-[760px]"
      >
        <motion.div
          variants={varBadge}
          className="font-mono uppercase tracking-[0.18em] text-[var(--color-acc)]"
          style={{ fontSize: "var(--fs-eyebrow)" }}
        >
          05 — Methods
        </motion.div>
        <motion.h2
          variants={varSectionHead}
          className="mt-3 font-editorial text-balance leading-[1.05] tracking-[-0.02em] text-[var(--color-fg-0)]"
          style={{ fontSize: "var(--fs-h2)" }}
        >
          How it works, <em>end to end</em>.
        </motion.h2>
        <motion.p
          variants={{
            hidden: { opacity: 0, y: 12 },
            show:   { opacity: 1, y: 0, transition: { ...spring.card } },
          }}
          className="mt-3 text-pretty text-[var(--color-fg-2)]"
          style={{ fontSize: "var(--fs-body)" }}
        >
          Knowledge graph embedding + graph heuristic + traceable provenance. Every prediction
          can be opened and read.
        </motion.p>
      </motion.div>

      {/* Card grid — exponential stagger, each card depth-shifted */}
      <motion.div
        ref={gridRef}
        variants={orchCards}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-40px" }}
        className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
      >
        {PIPELINE.map((s, i) => (
          <motion.div
            key={s.title}
            variants={varCard}
            className="method-card depth rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5"
            style={{ willChange: "transform, box-shadow, border-color" }}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] tabular text-[var(--color-fg-3)]">
                0{i + 1}
              </span>
              <motion.span
                whileHover={{ rotate: 12, scale: 1.18 }}
                transition={{ ...spring.snap }}
              >
                <s.icon size={15} className="text-[var(--color-acc)]" />
              </motion.span>
            </div>
            <div className="mt-3 font-display text-[16px] font-semibold text-[var(--color-fg-0)]">
              {s.title}
            </div>
            <p className="mt-1.5 text-[12.5px] leading-[1.55] text-[var(--color-fg-2)]">{s.body}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Equation strip */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ ...spring.card, delay: 0.18 }}
        className="mt-6 overflow-x-auto rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5"
      >
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
      </motion.div>
    </section>
  );
}
