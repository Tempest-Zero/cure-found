/**
 * CureFound — Expressive Motion System
 *
 * Philosophy: boutique weight hierarchy.
 *   Heavy elements (display type, hero) → high stiffness + mass > 1, over-travel on exit
 *   Mid elements (section headers, cards) → crisp snap with fast settle
 *   Light elements (eyebrows, captions, badges) → near-instant with a short tail
 *
 * Springs: HIGH stiffness (200-600), LOW damping (10-22), mass scaled by visual weight.
 * Easings: zero linear — expo/quint out for entrances, expo/quart inOut for scrubs.
 * Staggers: exponential cascade, not flat.
 */

// ─── Easing curves ────────────────────────────────────────────────────────────

export const ease = {
  /** Expo out — brutal snap-in for heavy display type */
  expo:    [0.16, 1, 0.3, 1]    as [number,number,number,number],
  /** Quint out — snappy for card/section reveals */
  quint:   [0.22, 1, 0.36, 1]   as [number,number,number,number],
  /** Quart inOut — used only for scrubbed/reversible scroll transitions */
  quartIO: [0.76, 0, 0.24, 1]   as [number,number,number,number],
  /** Back out — slight overshoot for CTAs and interactive elements */
  back:    [0.34, 1.56, 0.64, 1] as [number,number,number,number],
  /** Anticipate in — pull back then release, used on primary button press */
  pull:    [0.36, 0, 0.66, -0.56] as [number,number,number,number],
} as const;

// ─── Spring presets ───────────────────────────────────────────────────────────

export const spring = {
  /**
   * Hero / display — maximum snap, high mass gives weight to large type.
   * Settles in ~380ms with zero linear decay.
   */
  hero: { type: "spring", stiffness: 520, damping: 22, mass: 1.4 } as const,

  /**
   * Card / section header — snappy with slight authority.
   * Settles in ~260ms.
   */
  card: { type: "spring", stiffness: 380, damping: 18, mass: 1.0 } as const,

  /**
   * Tight UI — badges, eyebrows, captions.
   * Near-instant (settles ~180ms) with no oscillation.
   */
  tight: { type: "spring", stiffness: 600, damping: 28, mass: 0.7 } as const,

  /**
   * NumberTicker — high stiffness count-up.
   * Overshoots, then snaps to value with authority.
   */
  ticker: { stiffness: 280, damping: 14, mass: 1.1 },

  /**
   * Hover microinteraction — instant-feeling snap.
   */
  snap: { type: "spring", stiffness: 700, damping: 30, mass: 0.5 } as const,

  /**
   * Float / ambient — loose drift for canvas nodes.
   * Low stiffness + high damping to feel weightless.
   */
  float: { stiffness: 28, damping: 14, mass: 1.8 },
} as const;

// ─── Duration scale (for non-spring transitions only) ─────────────────────────

export const dur = {
  instant: 0.12,
  fast:    0.22,
  std:     0.42,
  slow:    0.65,
  crawl:   1.1,
} as const;

// ─── Stagger presets — exponential cascade ────────────────────────────────────

/** Linear stagger for small counts (2-4 items). */
export const staggerFlat = (base = 0.07) => ({
  staggerChildren: base,
  delayChildren:   0.08,
});

/** Exponential cascade — each child's delay = base * 1.18^i via GSAP stagger object. */
export const staggerWave = (base = 0.055) => ({
  staggerChildren: base,
  delayChildren:   0.06,
});

/** Radial stagger from center outward — use with GSAP's `from: "center"`. */
export const staggerRadial = {
  each:  0.04,
  from:  "center" as const,
  ease:  "power3.out",
};

// ─── Framer Motion variant factories ──────────────────────────────────────────

/** Heavy display entrance — large type feels massive landing in */
export const varHeroTitle = {
  hidden: { opacity: 0, y: 28,  filter: "blur(6px)" },
  show:   { opacity: 1, y: 0,   filter: "blur(0px)", transition: { ...spring.hero } },
};

/** Section header — authoritative drop */
export const varSectionHead = {
  hidden: { opacity: 0, y: 18 },
  show:   { opacity: 1, y: 0,  transition: { ...spring.card } },
};

/** Card entrance — crisp with forward momentum */
export const varCard = {
  hidden: { opacity: 0, y: 20, scale: 0.97 },
  show:   { opacity: 1, y: 0,  scale: 1,    transition: { ...spring.card } },
};

/** Light badge / eyebrow — snaps immediately */
export const varBadge = {
  hidden: { opacity: 0, y: 8,  scale: 0.94 },
  show:   { opacity: 1, y: 0,  scale: 1,    transition: { ...spring.tight } },
};

/** Stat card — comes in with a slight over-travel */
export const varStat = {
  hidden: { opacity: 0, y: 14, scale: 0.95 },
  show:   { opacity: 1, y: 0,  scale: 1,    transition: { ...spring.snap } },
};

/** Exit variant — fast, slight up-fade. Combine with AnimatePresence. */
export const varExit = {
  opacity: 0, y: -8, transition: { duration: dur.fast, ease: ease.expo },
};

// ─── Container orchestration (pass to parent motion.div variants) ─────────────

export const orchHero = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.11, delayChildren: 0.1 } },
};

export const orchCards = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.065, delayChildren: 0.08 } },
};

export const orchStats = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.09, delayChildren: 0.22 } },
};

// ─── GSAP ease strings ────────────────────────────────────────────────────────

export const gsapEase = {
  /** Expo out — for entrances and reveals */
  expo:      "expo.out",
  /** Power3 out — snappy card reveals */
  snap:      "power3.out",
  /** Sine inOut — ambient/idle drift only */
  drift:     "sine.inOut",
  /** None — for scrubbed scroll (must be linear) */
  scrub:     "none",
  /** Back out — slight overshoot for interactive pops */
  back:      "back.out(1.4)",
  /** Elastic small — micro-interaction punctuation */
  elastic:   "elastic.out(1, 0.4)",
} as const;

// ─── GSAP scroll scrub values ─────────────────────────────────────────────────
/** Scrub values control inertia lag. Higher = more inertia. */
export const scrub = {
  tight:  0.3,   // almost immediate catch-up
  normal: 0.8,   // slight lag — boutique smoothness
  heavy:  1.6,   // parallax background layers feel weighty
  crawl:  2.4,   // hero section exit — maximum mass
} as const;

// ─── Depth layer parallax rates ───────────────────────────────────────────────
/** Multiply by scroll distance to get layer travel distance. */
export const parallaxRate = {
  bg:         0.55,   // slowest — far background
  midBg:      0.30,
  mid:        0.10,
  midFg:     -0.08,
  fg:        -0.22,   // fastest — foreground lifts toward viewer
} as const;
