import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import cytoscape from "cytoscape";
import { EDGES, ENTITY_COLORS, NODE_TYPE } from "@/lib/data";

export function ExplorerSection() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const ids = new Set<string>();
    EDGES.forEach(([a, , b]) => { ids.add(a); ids.add(b); });

    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...[...ids].map((id) => ({
          data: { id, type: NODE_TYPE[id] ?? "Gene" },
        })),
        ...EDGES.map(([s, r, t], i) => ({
          data: { id: `e${i}`, source: s, target: t, label: r },
        })),
      ],
      layout: {
        name: "cose",
        animate: false,
        idealEdgeLength: () => 90,
        nodeRepulsion: () => 9000,
        padding: 30,
      } as any,
      wheelSensitivity: 0.2,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (n: any) => resolveCSSVar(ENTITY_COLORS[n.data("type") as keyof typeof ENTITY_COLORS] ?? "var(--color-fg-2)"),
            "label": "data(id)",
            "font-family": "JetBrains Mono, monospace",
            "font-size": 9,
            "color": "#E8E9EC",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "text-outline-color": "#0A0A0B",
            "text-outline-width": 2,
            "border-width": 1,
            "border-color": "#0A0A0B",
            "width": 14,
            "height": 14,
          } as any,
        },
        {
          selector: "edge",
          style: {
            "line-color": "rgba(127,184,255,0.18)",
            "target-arrow-color": "rgba(127,184,255,0.35)",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            "width": 1,
            "curve-style": "bezier",
          } as any,
        },
        {
          selector: "node:selected",
          style: { "border-color": "#5EE38B", "border-width": 2 } as any,
        },
        {
          selector: "edge.hl",
          style: { "line-color": "#5EE38B", "target-arrow-color": "#5EE38B", "width": 2, "z-index": 999 } as any,
        },
      ],
    });

    cy.on("tap", "node", (evt) => {
      const n = evt.target;
      cy.elements().removeClass("hl");
      n.connectedEdges().addClass("hl");
    });

    return () => cy.destroy();
  }, []);

  return (
    <section id="explorer" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-[720px]"
      >
        <div className="font-mono uppercase tracking-[0.18em] text-[var(--color-acc)]" style={{ fontSize: 'var(--fs-eyebrow)' }}>
          04 — Graph
        </div>
        <h2 className="mt-3 font-editorial text-balance leading-[1.05] tracking-[-0.02em] text-[var(--color-fg-0)]" style={{ fontSize: 'var(--fs-h2)' }}>
          The whole <em>knowledge graph</em>, browsable.
        </h2>
        <p className="mt-3 text-pretty text-[var(--color-fg-2)]" style={{ fontSize: 'var(--fs-body)' }}>
          673 nodes · 1,057 edges · 7 relation types. Click a node to highlight its neighborhood.
        </p>
      </motion.div>

      <div className="mt-8 rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
        <div className="flex items-center justify-between border-b border-[var(--color-line)] px-5 py-3">
          <div className="flex flex-wrap items-center gap-3">
            {(["Disease","Drug","Gene","Protein","Pathway","Symptom"] as const).map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-2)]">
                <span className="h-2 w-2 rounded-full" style={{ background: ENTITY_COLORS[t] }} />
                {t}
              </span>
            ))}
          </div>
          <span className="font-mono text-[10px] text-[var(--color-fg-3)]">drag · zoom · click</span>
        </div>
        <div ref={ref} className="h-[560px] w-full" />
      </div>
    </section>
  );
}

function resolveCSSVar(v: string): string {
  if (!v.startsWith("var(")) return v;
  const name = v.slice(4, -1).trim();
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#9398A1";
}
