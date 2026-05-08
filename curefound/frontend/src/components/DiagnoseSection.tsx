import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { spring, varSectionHead, varBadge } from "@/lib/motion";
import { AlertCircle, Stethoscope, X } from "lucide-react";
import { KGPulse } from "./KGPulse";
import {
  DIAGNOSE_PRESETS,
  NODE_BY_ID,
  SYMPTOMS,
  type DiagnoseResponse,
} from "@/lib/data";
import { api, cn } from "@/lib/utils";
import { ApiStatusChip } from "./ApiStatusChip";

const EMPTY_DIAGNOSE: DiagnoseResponse = {
  resolved_inputs: [],
  unresolved_inputs: [],
  candidates: [],
};

/**
 * POST /diagnose — schema in app/diagnose/schemas.py.
 * Request:  { symptoms: ["S:NAME" | "HP:NNNNNNN"], top_k }
 * Response: { resolved_inputs, unresolved_inputs, candidates: [...] }
 */
export function DiagnoseSection() {
  const [picked, setPicked] = useState<string[]>(DIAGNOSE_PRESETS[0].symptoms);
  const [loading, setLoading] = useState(false);
  const [topK, setTopK] = useState(8);
  const [data, setData] = useState<DiagnoseResponse>(EMPTY_DIAGNOSE);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastApiState, setLastApiState] = useState<"live" | "offline" | null>(null);

  async function run() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const r = await api<DiagnoseResponse>("/diagnose", {
        method: "POST",
        body: JSON.stringify({ symptoms: picked, top_k: topK }),
      });
      setData(r);
      setLastApiState("live");
    } catch (err) {
      setData(EMPTY_DIAGNOSE);
      setLastApiState("offline");
      setErrorMsg(
        err instanceof Error ? err.message : "Backend unreachable — check the API server.",
      );
    } finally {
      setLoading(false);
    }
  }

  // Auto-run on mount with the default preset.
  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(id: string) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  function applyPreset(symptoms: string[]) {
    setPicked(symptoms);
  }

  return (
    <section id="diagnose" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      <div className="flex flex-wrap items-start justify-between gap-3">
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
          <motion.div variants={varBadge} className="font-mono uppercase tracking-[0.18em] text-[var(--color-acc)]" style={{ fontSize: "var(--fs-eyebrow)" }}>
            03 — Diagnose
          </motion.div>
          <motion.h2 variants={varSectionHead} className="mt-3 font-display font-semibold leading-[1.1] tracking-[-0.015em] text-[var(--color-fg-0)]" style={{ fontSize: "var(--fs-h2)" }}>
            From symptoms to candidate diseases.
          </motion.h2>
          <motion.p
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { ...spring.card } } }}
            className="mt-3 text-pretty text-[var(--color-fg-2)]"
            style={{ fontSize: "var(--fs-body)" }}
          >
            Pick HPO-aligned symptoms — the API runs Jaccard + smoothed-IDF over the KG&apos;s{" "}
            <code className="font-mono text-[var(--color-fg-1)]">HAS_PHENOTYPE</code> edges and
            fuses both rankings via RRF. Useful as a triage hint, not a diagnosis.
          </motion.p>
        </motion.div>
        <ApiStatusChip sourceLabel="Jaccard+IDF" lastRequestState={lastApiState} className="mt-2" />
      </div>

      {/* Preset chips */}
      <div className="mt-7 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          quick presets
        </span>
        {DIAGNOSE_PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => applyPreset(p.symptoms)}
            className="lift group inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-3 py-1.5 font-mono text-[11px] text-[var(--color-fg-2)] transition-colors hover:border-[var(--color-acc)]/40 hover:text-[var(--color-fg-1)]"
            title={p.hint}
          >
            <span>{p.label}</span>
            <span className="text-[var(--color-fg-3)] group-hover:text-[var(--color-acc)]">
              {p.symptoms.length}
            </span>
          </button>
        ))}
      </div>

      <div className="mt-7 grid gap-4 lg:grid-cols-2">
        {/* Symptom picker */}
        <div className="tilt rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)] p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
              Symptoms · {picked.length} selected
            </span>
            {picked.length > 0 && (
              <button
                onClick={() => setPicked([])}
                className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--color-fg-3)] hover:text-[var(--color-fg-1)]"
              >
                <X size={11} /> clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {SYMPTOMS.map((s) => {
              const on = picked.includes(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => toggle(s.id)}
                  className={cn(
                    "lift rounded-full border px-3 py-1.5 font-mono text-[11px] transition-colors",
                    on
                      ? "border-[var(--color-acc)] bg-[var(--color-acc)]/12 text-[var(--color-acc)]"
                      : "border-[var(--color-line-2)] bg-[var(--color-bg-2)] text-[var(--color-fg-2)] hover:text-[var(--color-fg-1)]",
                  )}
                  title={s.id}
                >
                  {s.name}
                </button>
              );
            })}
          </div>
          <div className="mt-5 flex items-center justify-between">
            <div className="flex items-center gap-2 font-mono text-[10px] text-[var(--color-fg-3)]">
              <span className="uppercase tracking-wider">Top K</span>
              <input
                type="range"
                min={3}
                max={10}
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="accent-[var(--color-acc)]"
              />
              <span className="tabular text-[var(--color-fg-1)]">{topK}</span>
            </div>
            <button
              onClick={() => void run()}
              disabled={loading || picked.length === 0}
              className="lift inline-flex items-center gap-1.5 rounded-md bg-[var(--color-acc)] px-3 py-1.5 text-[13px] font-medium text-[#001a07] hover:bg-[var(--color-acc-2)] disabled:opacity-60"
            >
              {loading ? <KGPulse size={13} /> : <Stethoscope size={13} />}
              Diagnose
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="tilt rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
          <div className="flex items-center justify-between border-b border-[var(--color-line)] px-5 py-3">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
              Candidate diseases · {data.candidates.length}
            </span>
            <span className="font-mono text-[10px] text-[var(--color-fg-3)]">
              jaccard + idf · RRF k=60
            </span>
          </div>

          {data.unresolved_inputs.length > 0 && (
            <div className="flex items-start gap-2 border-b border-[var(--color-line)] bg-[var(--color-warn)]/8 px-5 py-2.5">
              <AlertCircle size={13} className="mt-0.5 shrink-0 text-[var(--color-warn)]" />
              <div className="font-mono text-[11px] text-[var(--color-fg-1)]">
                <span className="text-[var(--color-warn)]">unresolved:</span>{" "}
                <span className="text-[var(--color-fg-2)]">
                  {data.unresolved_inputs.join(", ")}
                </span>
              </div>
            </div>
          )}

          <ul className="divide-y divide-[var(--color-line)]">
            {data.candidates.length === 0 && !loading && (
              <li className="px-5 py-8 text-center text-[13px] text-[var(--color-fg-3)]">
                {errorMsg ? (
                  <>
                    <span className="block text-[var(--color-warn)]">Backend unreachable</span>
                    <span className="mt-1 block font-mono text-[10px]">{errorMsg}</span>
                    <button
                      onClick={() => void run()}
                      className="mt-3 inline-flex items-center gap-1 rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-1)] hover:border-[var(--color-acc)]/40"
                    >
                      retry
                    </button>
                  </>
                ) : (
                  <>Pick one or more symptoms, then click Diagnose.</>
                )}
              </li>
            )}
            {loading && data.candidates.length === 0 && (
              <>
                {Array.from({ length: 5 }).map((_, i) => (
                  <li key={i} className="flex items-center gap-4 px-5 py-3">
                    <span className="skeleton h-4 w-7" />
                    <span className="flex-1 space-y-1.5">
                      <span className="skeleton block h-4 w-40" />
                      <span className="skeleton block h-3 w-56" />
                    </span>
                    <span className="skeleton h-1.5 w-24 rounded-full" />
                    <span className="skeleton h-4 w-10" />
                  </li>
                ))}
              </>
            )}
            {data.candidates.slice(0, topK).map((c, i) => (
              <li key={c.disease_id} className="px-5 py-3">
                <div className="flex items-center gap-4">
                  <span className="w-7 font-mono text-[11px] text-[var(--color-fg-3)]">#{i + 1}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[13px] text-[var(--color-fg-0)]">
                        {c.disease_name}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-fg-3)]">{c.disease_id}</span>
                      {c.is_rare && (
                        <span className="rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[var(--color-fg-2)]">
                          rare
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-[var(--color-fg-3)]">
                      jaccard {c.jaccard_score.toFixed(3)} · idf {c.idf_score.toFixed(2)} · fused {c.fused_score.toFixed(4)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--color-bg-3)]">
                      <motion.span
                        key={c.disease_id + i}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.round(c.jaccard_score * 100)}%` }}
                        transition={{ ...spring.card }}
                        className="block h-full bg-[var(--color-acc)]"
                      />
                    </span>
                    <span className="w-12 text-right font-mono tabular text-[12px] text-[var(--color-fg-1)]">
                      {(c.jaccard_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                {c.matched_symptoms.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 pl-11">
                    {c.matched_symptoms.map((m) => (
                      <span
                        key={m.id}
                        className="inline-flex items-center rounded-full border border-[var(--color-acc)]/40 bg-[var(--color-acc)]/10 px-2 py-0.5 font-mono text-[10px] text-[var(--color-acc)]"
                      >
                        {NODE_BY_ID[m.id]?.name ?? m.name ?? m.id}
                      </span>
                    ))}
                    {c.missing_symptoms.slice(0, 3).map((m) => (
                      <span
                        key={m.id}
                        className="inline-flex items-center rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-0.5 font-mono text-[10px] text-[var(--color-fg-3)] line-through"
                      >
                        {NODE_BY_ID[m.id]?.name ?? m.name ?? m.id}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>

        </div>
      </div>
    </section>
  );
}
