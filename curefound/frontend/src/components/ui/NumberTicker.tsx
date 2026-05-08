/**
 * NumberTicker — animated count-up from 0 to target value on viewport entry.
 * Adapted from Magic UI (magicui.design), uses framer-motion (already installed).
 * No new dependencies.
 */
import { useEffect, useRef, useState } from "react";
import { motion, useInView, useMotionValue, useSpring } from "framer-motion";

interface NumberTickerProps {
  value: number;
  decimalPlaces?: number;
  className?: string;
  /** Duration-ish: spring stiffness. Lower = slower. Default 50. */
  stiffness?: number;
}

export function NumberTicker({
  value,
  decimalPlaces = 3,
  className,
  stiffness = 50,
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-50px" });
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, { stiffness, damping: 20, mass: 1 });
  const [display, setDisplay] = useState("0." + "0".repeat(decimalPlaces));

  useEffect(() => {
    if (isInView) {
      motionValue.set(value);
    }
  }, [isInView, value, motionValue]);

  useEffect(() => {
    const unsubscribe = spring.on("change", (v: number) => {
      setDisplay(v.toFixed(decimalPlaces));
    });
    return unsubscribe;
  }, [spring, decimalPlaces]);

  return (
    <motion.span ref={ref} className={className}>
      {display}
    </motion.span>
  );
}
