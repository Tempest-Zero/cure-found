import { useEffect, useRef } from "react";
import gsap from "gsap";
import { EDGES, NODE_TYPE, ENTITY_COLORS, type EntityType } from "@/lib/data";

/**
 * Hero KG ambient backdrop — force-laid, GSAP-driven slow drift,
 * rendered to canvas. Caps at ~60 visible nodes for perf.
 *
 * Skill rules respected: motion-meaning (drift conveys "live graph"),
 * reduced-motion guard, no decorative-only blur.
 */
export function HeroKGCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let W = 0, H = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    type Node = { id: string; type: EntityType; x: number; y: number; vx: number; vy: number; r: number };
    const ids = new Set<string>();
    EDGES.forEach(([a, , b]) => { ids.add(a); ids.add(b); });
    const nodeIds = [...ids].slice(0, 60);
    const nodes: Node[] = nodeIds.map((id) => ({
      id,
      type: (NODE_TYPE[id] ?? "Gene") as EntityType,
      x: Math.random(), y: Math.random(),
      vx: 0, vy: 0,
      r: NODE_TYPE[id] === "Disease" ? 4 : NODE_TYPE[id] === "Drug" ? 3.4 : 2.6,
    }));
    const idx = new Map(nodes.map((n, i) => [n.id, i]));
    const links = EDGES
      .filter(([a, , b]) => idx.has(a) && idx.has(b))
      .map(([a, , b]) => [idx.get(a)!, idx.get(b)!] as [number, number]);

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      W = rect.width; H = rect.height;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    // Lay out: simple repulsion + spring (fixed iterations for determinism)
    nodes.forEach(n => { n.x = n.x * W; n.y = n.y * H; });
    for (let it = 0; it < 220; it++) {
      for (let i = 0; i < nodes.length; i++) {
        let fx = 0, fy = 0;
        const a = nodes[i];
        for (let j = 0; j < nodes.length; j++) {
          if (i === j) continue;
          const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          const d2 = dx * dx + dy * dy + 0.01;
          const f = 2400 / d2;
          fx += dx * f; fy += dy * f;
        }
        // center pull
        fx += (W / 2 - a.x) * 0.002;
        fy += (H / 2 - a.y) * 0.002;
        a.vx = (a.vx + fx) * 0.5;
        a.vy = (a.vy + fy) * 0.5;
      }
      for (const [i, j] of links) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const target = 90;
        const f = (d - target) * 0.04;
        const nx = dx / d * f, ny = dy / d * f;
        a.vx += nx; a.vy += ny;
        b.vx -= nx; b.vy -= ny;
      }
      for (const n of nodes) {
        n.x += n.vx * 0.02;
        n.y += n.vy * 0.02;
        n.x = Math.max(20, Math.min(W - 20, n.x));
        n.y = Math.max(20, Math.min(H - 20, n.y));
      }
    }

    if (!reduceMotion) {
      nodes.forEach((n, i) => {
        // Larger nodes (Disease/Drug) are "heavier" — smaller drift range, slower period
        const weight = n.r > 3 ? 0.55 : n.r > 2.8 ? 0.8 : 1.2;
        const range  = 20 * weight;
        const period = (7 + Math.random() * 6) / weight;

        gsap.to(n, {
          x: n.x + (Math.random() - 0.5) * range,
          y: n.y + (Math.random() - 0.5) * range,
          duration: period,
          repeat: -1,
          yoyo: true,
          // Expo-out for heavy nodes, sine for light — mass-differentiated feel
          ease: n.r > 3 ? "expo.inOut" : "sine.inOut",
          delay: i * 0.038,
        });
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      // edges
      ctx.lineWidth = 1;
      for (const [i, j] of links) {
        const a = nodes[i], b = nodes[j];
        const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        grad.addColorStop(0, "rgba(94,227,139,0.18)");
        grad.addColorStop(1, "rgba(127,184,255,0.10)");
        ctx.strokeStyle = grad;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      // nodes
      for (const n of nodes) {
        const c = ENTITY_COLORS[n.type] ?? "var(--color-fg-2)";
        ctx.fillStyle = resolveCSSVar(c);
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(10,10,11,0.6)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      animRef.current = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      window.removeEventListener("resize", resize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
      gsap.killTweensOf(nodes);
    };
  }, []);

  return <canvas ref={ref} className="absolute inset-0 h-full w-full" aria-hidden />;
}

function resolveCSSVar(v: string): string {
  if (!v.startsWith("var(")) return v;
  const name = v.slice(4, -1).trim();
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#5EE38B";
}
