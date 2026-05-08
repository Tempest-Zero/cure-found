/**
 * Single GSAP registration point.
 * Every component that uses GSAP must import from this file.
 * Do NOT register the plugin again elsewhere.
 */
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// Honor reduced-motion globally — kills all GSAP timelines.
if (typeof window !== "undefined") {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (mq.matches) gsap.globalTimeline.timeScale(0);
}

export { gsap, ScrollTrigger };
