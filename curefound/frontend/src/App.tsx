import { ArrowRight, ExternalLink, Github, ShieldAlert } from "lucide-react";
import { motion } from "framer-motion";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import {
  ease, spring, dur, scrub, parallaxRate,
  varHeroTitle, varBadge, varStat,
  orchHero, orchStats,
} from "@/lib/motion";
import { NumberTicker } from "./components/ui/NumberTicker";
import { BackgroundBeams, Spotlight } from "./components/aceternity";
import { RepurposeSection } from "./components/RepurposeSection";
import { DiagnoseSection } from "./components/DiagnoseSection";
import { EvalSection } from "./components/EvalSection";
import { MethodsSection } from "./components/MethodsSection";
import { Footer } from "./components/Footer";

// Lazy-load heavy components — Cytoscape (Explorer) and GSAP (HeroKG) are
// >200 KB each, and the explorer is below the fold. Defer them so the
// initial paint stays light.
const HeroKGCanvas = lazy(() =>
  import("./components/HeroKGCanvas").then((m) => ({ default: m.HeroKGCanvas })),
);
const ExplorerSection = lazy(() =>
  import("./components/ExplorerSection").then((m) => ({ default: m.ExplorerSection })),
);

export default function App() {
  return (
    <div className="relative min-h-screen bg-[var(--color-bg-0)] text-[var(--color-fg-1)]">
      <NavBar />
      <Hero />
      <RepurposeSection />
      <EvalSection />
      <DiagnoseSection />
      <Suspense
        fallback={
          <div className="mx-auto max-w-[1200px] px-6 py-24 text-center font-mono text-[11px] uppercase tracking-wider text-[var(--color-fg-3)]">
            loading explorer…
          </div>
        }
      >
        <ExplorerSection />
      </Suspense>
      <MethodsSection />
      <Footer />
    </div>
  );
}

function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 ${
        scrolled ? "backdrop-blur-md bg-[rgba(10,10,11,0.72)] border-b border-[var(--color-line)]" : ""
      }`}
      style={{
        transition: `background ${dur.std}s cubic-bezier(${ease.quint.join(",")})`,
      }}
    >
      <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-3.5">
        <a href="#top" className="flex items-center gap-2.5">
          <LogoMark />
          <span className="font-display text-[15px] font-semibold tracking-tight">CureFound</span>
          <span className="ml-2 hidden rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-2)] sm:inline">
            research
          </span>
        </a>
        <nav className="hidden items-center gap-7 text-[13px] text-[var(--color-fg-2)] md:flex">
          <a href="#repurpose" className="hover:text-[var(--color-fg-1)]">Repurpose</a>
          <a href="#eval" className="hover:text-[var(--color-fg-1)]">Eval</a>
          <a href="#diagnose" className="hover:text-[var(--color-fg-1)]">Diagnose</a>
          <a href="#explorer" className="hover:text-[var(--color-fg-1)]">Graph</a>
          <a href="#methods" className="hover:text-[var(--color-fg-1)]">Methods</a>
        </nav>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/Tempest-Zero/cure-found"
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1.5 rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-fg-2)] hover:text-[var(--color-fg-1)] sm:inline-flex"
          >
            <Github size={14} /> Code
          </a>
          <a
            href="#repurpose"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-acc)] px-3 py-1.5 text-[12px] font-medium text-[#001a07] hover:bg-[var(--color-acc-2)]"
          >
            Try it <ArrowRight size={13} />
          </a>
        </div>
      </div>
    </header>
  );
}

function LogoMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="3" fill="var(--color-acc)" />
      <circle cx="4" cy="6" r="1.6" fill="var(--color-t-protein)" />
      <circle cx="20" cy="6" r="1.6" fill="var(--color-t-gene)" />
      <circle cx="4" cy="18" r="1.6" fill="var(--color-t-pathway)" />
      <circle cx="20" cy="18" r="1.6" fill="var(--color-t-disease)" />
      <path d="M12 12L4 6M12 12L20 6M12 12L4 18M12 12L20 18" stroke="var(--color-line-2)" strokeWidth="1" />
    </svg>
  );
}


function Hero() {
  const sectionRef    = useRef<HTMLDivElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const beamsRef      = useRef<HTMLDivElement>(null);
  const contentRef    = useRef<HTMLDivElement>(null);
  const warningRef    = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sectionRef.current) return;
    const ctx = gsap.context(() => {
      const trig = { trigger: sectionRef.current!, start: "top top", end: "bottom top" };

      // Deep background layer — slowest, maximum mass
      gsap.to(canvasWrapRef.current, {
        scrollTrigger: { ...trig, scrub: scrub.crawl },
        y: `${parallaxRate.bg * 100}%`,
        scale: 1.12,
        opacity: 0.4,
      });

      // Beams midground — slightly faster than canvas
      gsap.to(beamsRef.current, {
        scrollTrigger: { ...trig, scrub: scrub.heavy },
        y: `${parallaxRate.midBg * 100}%`,
        opacity: 0.3,
      });

      // Content foreground — moves up toward viewer as page scrolls
      gsap.to(contentRef.current, {
        scrollTrigger: { ...trig, scrub: scrub.normal },
        y: `${parallaxRate.fg * -60}px`,
        opacity: 0.0,
      });

      // Warning badge exits faster (lightweight)
      gsap.to(warningRef.current, {
        scrollTrigger: { ...trig, scrub: scrub.tight },
        y: `${parallaxRate.midFg * -40}px`,
        opacity: 0,
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} id="top" className="relative isolate overflow-hidden pb-24 pt-32 sm:pt-40">
      <Spotlight />

      {/* Background layer — slowest parallax */}
      <div ref={canvasWrapRef} className="absolute inset-0 spotlight-mask" style={{ willChange: "transform, opacity" }}>
        <Suspense fallback={null}>
          <HeroKGCanvas />
        </Suspense>
      </div>

      {/* Midground layer — beams */}
      <div ref={beamsRef} className="absolute inset-0 pointer-events-none" style={{ willChange: "transform, opacity" }}>
        <BackgroundBeams className="opacity-70" />
      </div>

      {/* Foreground content */}
      <div ref={contentRef} className="relative mx-auto max-w-[1200px] px-6" style={{ willChange: "transform, opacity" }}>
        <motion.div
          variants={orchHero}
          initial="hidden"
          animate="show"
          className="mx-auto max-w-[820px] text-center"
        >
          {/* Badge — snaps in first, tight spring */}
          <motion.div variants={varBadge} className="mb-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)]/70 px-3 py-1 font-mono text-[11px] text-[var(--color-fg-2)] backdrop-blur">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-acc)] shadow-[0_0_10px_var(--color-acc)]" />
              RotatE · 673 nodes · 1,057 edges · 13 rare diseases
            </span>
          </motion.div>

          {/* Display title — heavyweight entrance with blur */}
          <motion.h1
            variants={varHeroTitle}
            className="font-display text-balance font-semibold leading-[1.05] tracking-[-0.02em]"
            style={{ fontSize: "var(--fs-display)" }}
          >
            Predict repurposable drugs
            <br />
            for <span className="text-[var(--color-acc)]">rare lysosomal disorders</span>.
          </motion.h1>

          {/* Body copy — standard card spring */}
          <motion.p
            variants={{
              hidden: { opacity: 0, y: 14 },
              show:   { opacity: 1, y: 0, transition: { ...spring.card } },
            }}
            className="mx-auto mt-6 max-w-[640px] text-pretty leading-[1.6] text-[var(--color-fg-2)]"
            style={{ fontSize: "var(--fs-body)" }}
          >
            CureFound learns complex-valued relational rotations over a curated KG of diseases,
            drugs, proteins, and pathways — then ranks plausible drug candidates with the full
            evidence path attached.
          </motion.p>

          {/* CTAs — back-out overshoot on enter */}
          <motion.div
            variants={{
              hidden: { opacity: 0, y: 12, scale: 0.97 },
              show:   { opacity: 1, y: 0,  scale: 1, transition: { ...spring.snap } },
            }}
            className="mt-8 flex flex-wrap items-center justify-center gap-3"
          >
            <a
              href="#repurpose"
              className="lift group inline-flex items-center gap-2 rounded-md bg-[var(--color-acc)] px-4 py-2.5 text-[14px] font-medium text-[#001a07] hover:bg-[var(--color-acc-2)]"
            >
              Try the demo
              <ArrowRight
                size={15}
                className="transition-transform duration-200 group-hover:translate-x-1"
                style={{ transitionTimingFunction: `cubic-bezier(${ease.back.join(",")})` }}
              />
            </a>
            <a
              href="#methods"
              className="lift inline-flex items-center gap-2 rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)]/60 px-4 py-2.5 text-[14px] text-[var(--color-fg-1)] backdrop-blur hover:border-[var(--color-fg-4)]"
            >
              Methods <ExternalLink size={13} />
            </a>
          </motion.div>

          {/* Stats — exponential cascade, each with snap spring */}
          <motion.div
            variants={orchStats}
            initial="hidden"
            animate="show"
            className="mx-auto mt-10 grid max-w-[760px] grid-cols-2 gap-3 sm:grid-cols-4"
          >
            <motion.div variants={varStat}><Stat label="MRR"     numValue={0.380} sub="vs 0.131 TransE" /></motion.div>
            <motion.div variants={varStat}><Stat label="Hits@1"  numValue={0.188} sub="first non-zero" /></motion.div>
            <motion.div variants={varStat}><Stat label="Hits@3"  numValue={0.375} sub="+506% vs TransE" /></motion.div>
            <motion.div variants={varStat}><Stat label="Hits@10" numValue={0.750} sub="+33% vs TransE" /></motion.div>
          </motion.div>
        </motion.div>

        <div ref={warningRef} className="mt-10 flex justify-center" style={{ willChange: "transform, opacity" }}>
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line)] bg-[var(--color-bg-1)]/80 px-3 py-1.5 backdrop-blur">
            <ShieldAlert size={13} className="text-[var(--color-warn)]" />
            <span className="font-mono text-[11px] text-[var(--color-fg-2)]">
              Research prototype. Not for clinical use.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function Stat({ label, numValue, sub }: { label: string; numValue: number; sub?: string }) {
  return (
    <div className="tilt rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-1)]/60 p-3 backdrop-blur">
      <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">{label}</div>
      <div className="mt-1 font-mono text-[22px] font-medium tabular text-[var(--color-fg-0)]">
        <NumberTicker value={numValue} decimalPlaces={3} />
      </div>
      {sub && (
        <div className="mt-0.5 font-mono text-[9px] text-[var(--color-fg-3)]">{sub}</div>
      )}
    </div>
  );
}
