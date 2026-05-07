import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/**
 * Aceternity-style BackgroundBeams — vertical animated beams over a faint grid.
 * MIT-licensed pattern, hand-ported (no upstream package).
 */
export function BackgroundBeams({ className }: { className?: string }) {
  const beams = [
    { left: "8%",  delay: 0,   dur: 7.5, hue: "var(--color-acc)" },
    { left: "22%", delay: 1.4, dur: 9.0, hue: "var(--color-t-protein)" },
    { left: "38%", delay: 0.6, dur: 6.4, hue: "var(--color-acc)" },
    { left: "52%", delay: 2.2, dur: 8.6, hue: "var(--color-t-gene)" },
    { left: "68%", delay: 0.9, dur: 7.0, hue: "var(--color-acc)" },
    { left: "82%", delay: 1.8, dur: 9.4, hue: "var(--color-t-pathway)" },
    { left: "94%", delay: 0.3, dur: 6.8, hue: "var(--color-acc)" },
  ];
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      <div className="absolute inset-0 bg-grid opacity-60" />
      {beams.map((b, i) => (
        <span
          key={i}
          className="absolute top-0 h-[40vh] w-px"
          style={{
            left: b.left,
            background: `linear-gradient(to bottom, transparent, ${b.hue}, transparent)`,
            animation: `beam ${b.dur}s linear ${b.delay}s infinite`,
            opacity: 0.55,
          }}
        />
      ))}
    </div>
  );
}

/** Aceternity-style Spotlight — soft radial glow that follows the section header. */
export function Spotlight({ className }: { className?: string }) {
  return (
    <div
      className={cn("pointer-events-none absolute -top-40 left-1/2 h-[640px] w-[1200px] -translate-x-1/2", className)}
      style={{
        background:
          "radial-gradient(ellipse at center, rgba(94,227,139,.18), rgba(94,227,139,.06) 30%, transparent 70%)",
        filter: "blur(40px)",
      }}
    />
  );
}

/** Aceternity-style MovingBorder — animated conic border. Use as a wrapper. */
export function MovingBorder({
  children,
  className,
  radius = 14,
}: {
  children: ReactNode;
  className?: string;
  radius?: number;
}) {
  return (
    <div className={cn("moving-border", className)} style={{ borderRadius: radius }}>
      {children}
    </div>
  );
}

/** Card3D — tilt on hover, MIT pattern. */
export function Card3D({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, rotateX: 1.4, rotateY: -1.4, transition: { duration: 0.2 } }}
      style={{ transformStyle: "preserve-3d", perspective: 800 }}
      className={cn("rounded-[14px]", className)}
    >
      {children}
    </motion.div>
  );
}

/** AnimatedTooltip — small badge that fades in on hover. */
export function AnimatedTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-1 font-mono text-[10px] text-[var(--color-fg-1)] opacity-0 transition-opacity duration-150 group-hover:opacity-100">
        {label}
      </span>
    </div>
  );
}
