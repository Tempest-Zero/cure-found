import { useEffect, useRef, useState } from "react";
import { motion, useInView, useMotionValue, useSpring } from "framer-motion";
import { spring as springPresets } from "@/lib/motion";

interface NumberTickerProps {
  value: number;
  decimalPlaces?: number;
  className?: string;
}

export function NumberTicker({ value, decimalPlaces = 3, className }: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-50px" });
  const motionValue = useMotionValue(0);
  // High stiffness + low damping: overshoots slightly then snaps to value
  const animated = useSpring(motionValue, springPresets.ticker);
  const [display, setDisplay] = useState("0." + "0".repeat(decimalPlaces));

  useEffect(() => {
    if (isInView) motionValue.set(value);
  }, [isInView, value, motionValue]);

  useEffect(() => {
    return animated.on("change", (v: number) => setDisplay(v.toFixed(decimalPlaces)));
  }, [animated, decimalPlaces]);

  return (
    <motion.span ref={ref} className={className}>
      {display}
    </motion.span>
  );
}
