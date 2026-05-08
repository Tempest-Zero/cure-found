import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, ChevronRight, FlaskConical, Sparkles } from "lucide-react";
import { KGPulse } from "./KGPulse";
import {
  DISEASES,
  ENTITY_COLORS,
  NODE_BY_ID,
  type EvidenceEdge,
  type RepurposeCandidate,
  type RepurposeResponse,
} from "@/lib/data";
import { api, cn, fetchAvailableModels, modelLabel, type ModelName } from "@/lib/utils";
import { MovingBorder } from "./aceternity";
import { ApiStatusChip } from "./ApiStatusChip";

/**
 * POST /repurpose — schema in app/repurpose/schemas.py.
 * Request:  { disease_id, top_k, include_already_approved, model }
 * Response: { disease_id, disease_name, candidates: [...] }
 *
 * `model` selects which KG-embedding backend scores the candidates:
 *   - rotate  : RotatE complex rotations (Sun 2019), always bundled
 *   - rgcn    : R-GCN (Schlichtkrull 2018) + DistMult head — optional
 *   - compgcn : CompGCN (Vashishth 2020) + DistMult head — optional
 *
 * The optional models load only if their .npz artifacts shipped with the
 * deploy (the Colab notebook produces them). GET /repurpose/models returns
 * the live set; we fetch it on mount and only render chips for those.
 */
const EMPTY_REPURPOSE: RepurposeResponse = {
  disease_id: "",
  disease_name: "",
  candidates: [],
};

export function RepurposeSection() {
  const [diseaseId, setDiseaseId] = useState("D:NPC");
  const [topK, setTopK] = useState(8);
  const [includeApproved, setIncludeApproved] = useState(false);
  const [model, setModel] = useState<ModelName>("rotate");
  const [availableModels, setAvailableModels] = useState<ModelName[]>(["rotate"]);
  const [data, setData] = useState<RepurposeResponse>(EMPTY_REPURPOSE);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastApiState, setLastApiState] = useState<"live" | "offline" | null>(null);

  const disease = useMemo(
    () => DISEASES.find((d) => d.id === diseaseId) ?? DISEASES[0],
    [diseaseId],
  );

  async function run() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const r = await api<RepurposeResponse>("/repurpose", {
        method: "POST",
        body: JSON.stringify({
          disease_id: diseaseId,
          top_k: topK,
          include_already_approved: includeApproved,
          model,
        }),
      });
      setData(r);
      setSelected(0);
      setLastApiState("live");
    } catch (err) {
      setData(EMPTY_REPURPOSE);
      setSelected(0);
      setLastApiState("offline");
      const msg = err instanceof Error ? err.message : "Backend unreachable — check the API server.";
      // 503 = the chosen model isn't loaded in this deploy. Fall back to RotatE
      // so the demo keeps working instead of leaving the user staring at an
      // error chip with no remedy.
      if (msg.startsWith("503") && model !== "rotate") {
        setModel("rotate");
        setErrorMsg(
          `Model "${modelLabel(model)}" isn't loaded in this deploy — falling back to RotatE.`,
        );
      } else {
        setErrorMsg(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  // Fetch available models once on mount. The default chip set is just
  // ["rotate"] so the UI renders something sensible while the call resolves.
  useEffect(() => {
    let alive = true;
    fetchAvailableModels().then((ms) => {
      if (!alive) return;
      setAvailableModels(ms);
      // If the current selection isn't loaded, fall back to the first option.
      if (!ms.includes(model)) setModel(ms[0] ?? "rotate");
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-run on mount + whenever the disease or model changes.
  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diseaseId, model]);

  const visibleCands = data.candidates.slice(0, topK);
  const sel = visibleCands[selected];

  return (
    <section id="repurpose" className="relative mx-auto max-w-[1200px] scroll-mt-24 px-6 py-24">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          eyebrow="01 — Repurpose"
          title="Rank candidate drugs for a rare disease."
          sub="Pick a disease — get a ranked list of drug candidates with the full evidence path through the KG, plus the model and graph scores behind each rank."
        />
        <ApiStatusChip sourceLabel={modelLabel(model)} lastRequestState={lastApiState} className="mt-2" />
      </div>

      <div className="mt-10 grid gap-4 lg:grid-cols-[440px_1fr]">
        {/* Left: input + ranked list */}
        <div className="flex flex-col gap-4">
          <MovingBorder radius={14} className="bg-[var(--color-bg-1)]">
            <div className="rounded-[14px] p-4">
              <label className="mb-2 block font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                Disease
              </label>
              <select
                value={diseaseId}
                onChange={(e) => setDiseaseId(e.target.value)}
                className="w-full rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-3 py-2.5 font-mono text-[13px] text-[var(--color-fg-1)] focus:border-[var(--color-acc)] focus:outline-none"
              >
                {DISEASES.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.id} — {d.name}
                  </option>
                ))}
              </select>

              <div className="mt-3">
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                  Model
                </label>
                <ModelChipGroup
                  available={availableModels}
                  selected={model}
                  onSelect={setModel}
                />
                <p className="mt-1.5 font-mono text-[10px] leading-relaxed text-[var(--color-fg-3)]">
                  Score per-model and per-retrain — never compare values across.
                </p>
              </div>

              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-[12px] text-[var(--color-fg-2)]">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                    Top K
                  </span>
                  <input
                    type="range"
                    min={3}
                    max={10}
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value))}
                    className="accent-[var(--color-acc)]"
                  />
                  <span className="font-mono tabular text-[var(--color-fg-1)]">{topK}</span>
                </div>
                <button
                  onClick={() => void run()}
                  disabled={loading}
                  className="lift inline-flex items-center gap-1.5 rounded-md bg-[var(--color-acc)] px-3 py-1.5 text-[13px] font-medium text-[#001a07] hover:bg-[var(--color-acc-2)] disabled:opacity-60"
                >
                  {loading ? <KGPulse size={13} /> : <FlaskConical size={13} />}
                  Predict
                </button>
              </div>

              <label className="mt-3 inline-flex cursor-pointer items-center gap-2 font-mono text-[11px] text-[var(--color-fg-2)]">
                <input
                  type="checkbox"
                  checked={includeApproved}
                  onChange={(e) => setIncludeApproved(e.target.checked)}
                  className="h-3.5 w-3.5 accent-[var(--color-acc)]"
                />
                include already-approved drugs
              </label>
            </div>
          </MovingBorder>

          <div className="rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
            <div className="flex items-center justify-between border-b border-[var(--color-line)] px-4 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                {disease.name} · {visibleCands.length} candidates
              </span>
              <span className="font-mono text-[10px] text-[var(--color-fg-3)]">RRF · k=60</span>
            </div>
            <ul className="max-h-[520px] divide-y divide-[var(--color-line)] overflow-y-auto">
              {visibleCands.map((c, i) => (
                <CandidateRow
                  key={c.drug_id}
                  c={c}
                  active={i === selected}
                  onClick={() => setSelected(i)}
                />
              ))}
              {visibleCands.length === 0 && !loading && (
                <li className="px-4 py-8 text-center text-[13px] text-[var(--color-fg-3)]">
                  {errorMsg ? (
                    <>
                      <span className="block text-[var(--color-warn)]">Backend unreachable</span>
                      <span className="mt-1 block font-mono text-[10px] text-[var(--color-fg-3)]">{errorMsg}</span>
                      <button
                        onClick={() => void run()}
                        className="mt-3 inline-flex items-center gap-1 rounded-md border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-1)] hover:border-[var(--color-acc)]/40"
                      >
                        retry
                      </button>
                    </>
                  ) : (
                    <>No candidates returned.</>
                  )}
                </li>
              )}
              {loading && visibleCands.length === 0 && (
                <>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                      <span className="skeleton h-4 w-7" />
                      <span className="flex-1 space-y-1.5">
                        <span className="skeleton block h-4 w-36" />
                        <span className="skeleton block h-3 w-52" />
                      </span>
                      <span className="skeleton h-1.5 w-16 rounded-full" />
                      <span className="skeleton h-4 w-14" />
                    </li>
                  ))}
                </>
              )}
            </ul>
          </div>
        </div>

        {/* Right: evidence path */}
        <div className="rounded-[14px] border border-[var(--color-line)] bg-[var(--color-bg-1)]">
          <div className="flex items-center justify-between border-b border-[var(--color-line)] px-5 py-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
                Evidence path
              </span>
              <span className="text-[13px] text-[var(--color-fg-1)]">
                <span className="font-mono">{sel?.drug_name ?? "—"}</span>{" "}
                <span className="text-[var(--color-fg-3)]">→</span>{" "}
                <span className="font-mono">{disease.name}</span>
              </span>
            </div>
            {sel && <ApprovalChip approved={sel.already_approved} year={sel.approval_year} />}
          </div>
          <div className="p-5 sm:p-7">
            <AnimatePresence mode="wait">
              <motion.div
                key={sel?.drug_id ?? "empty"}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                {sel ? (
                  <PathFigure paths={sel.evidence_paths} />
                ) : (
                  <div className="text-[var(--color-fg-3)]">No evidence path.</div>
                )}
              </motion.div>
            </AnimatePresence>
            {sel && (
              <div className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <ScoreBar label="model" value={sel.model_score} signedScore />
                <ScoreBar label="graph" value={sel.graph_score} />
                <ScoreBar label="fused" value={sel.fused_score} accent />
                <RankBox rank={sel.model_rank} graphRank={sel.graph_rank} />
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------- Candidate row ---------------------------- */
function CandidateRow({
  c, active, onClick,
}: {
  c: RepurposeCandidate;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={cn(
          "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
          active ? "bg-[var(--color-bg-2)]" : "hover:bg-[var(--color-bg-2)]/60",
        )}
      >
        <span className="w-7 text-right font-mono text-[11px] text-[var(--color-fg-3)]">
          #{c.model_rank}
        </span>
        <span className="flex-1">
          <span className="block font-mono text-[13px] text-[var(--color-fg-0)]">{c.drug_name}</span>
          <span className="block font-mono text-[10px] text-[var(--color-fg-3)]">
            <span className="text-[var(--color-fg-2)]">{c.drug_id}</span> · model {c.model_score.toFixed(3)} · graph {c.graph_score.toFixed(3)}
          </span>
        </span>
        <span className="flex items-center gap-2">
          {c.already_approved && (
            <span title="Already approved" aria-label="Already approved">
              <CheckCircle2 size={13} className="text-[var(--color-acc)]" />
            </span>
          )}
          <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-bg-3)] sm:block">
            <span
              className="block h-full bg-[var(--color-acc)]"
              style={{
                width: `${Math.min(100, Math.round(Math.max(0, c.fused_score) * 100 * 30))}%`,
              }}
            />
          </span>
          <span className="font-mono tabular text-[12px] text-[var(--color-fg-1)]">
            {c.fused_score.toFixed(4)}
          </span>
          <ChevronRight
            size={14}
            className={cn("text-[var(--color-fg-3)]", active && "text-[var(--color-acc)]")}
          />
        </span>
      </button>
    </li>
  );
}

/* ---------------------------- Path figure ----------------------------- */
function PathFigure({ paths }: { paths: EvidenceEdge[][] }) {
  if (!paths?.length) {
    return <div className="text-[var(--color-fg-3)]">No evidence path returned.</div>;
  }
  return (
    <div className="flex flex-col gap-4">
      {paths.slice(0, 3).map((path, pi) => (
        <div key={pi} className="flex flex-wrap items-center gap-2">
          {path.length > 0 && <NodeTile id={path[0].from} />}
          {path.map((edge, i) => (
            <span key={i} className="contents">
              <EdgeTile rel={edge.rel} dir={edge.direction ?? "forward"} action={edge.action} />
              <NodeTile id={edge.to} />
            </span>
          ))}
        </div>
      ))}
      {paths.length > 3 && (
        <span className="font-mono text-[10px] text-[var(--color-fg-3)]">
          + {paths.length - 3} more path{paths.length - 3 === 1 ? "" : "s"}
        </span>
      )}
    </div>
  );
}

function NodeTile({ id }: { id: string }) {
  const meta = NODE_BY_ID[id];
  const type = meta?.type ?? "Gene";
  const name = meta?.name ?? id;
  return (
    <div
      className="tilt rounded-lg border bg-[var(--color-bg-2)] px-3 py-2"
      style={{
        borderColor:
          "color-mix(in oklab, var(--color-line-2) 70%, " + ENTITY_COLORS[type] + " 30%)",
      }}
    >
      <div
        className="font-mono text-[9px] uppercase tracking-wider"
        style={{ color: ENTITY_COLORS[type] }}
      >
        {type}
      </div>
      <div className="font-mono text-[12px] text-[var(--color-fg-0)]">{id}</div>
      <div className="mt-0.5 max-w-[160px] truncate text-[11px] text-[var(--color-fg-2)]">{name}</div>
    </div>
  );
}

function EdgeTile({
  rel, dir, action,
}: {
  rel: string;
  dir: "forward" | "reverse";
  action?: string | null;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-1">
      <div className="flex items-center gap-1">
        {dir === "reverse" && <span className="font-mono text-[12px] text-[var(--color-fg-3)]">←</span>}
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-2)]">
          {rel}
        </span>
        {dir !== "reverse" && <span className="font-mono text-[12px] text-[var(--color-fg-3)]">→</span>}
      </div>
      {action && <span className="font-mono text-[9px] text-[var(--color-fg-3)]">{action}</span>}
    </div>
  );
}

/* ---------------------------- Approval chip ---------------------------- */
function ApprovalChip({ approved, year }: { approved: boolean; year: number | null }) {
  if (approved) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-acc)]/40 bg-[var(--color-acc)]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-acc)]">
        <span className="h-1 w-1 rounded-full bg-[var(--color-acc)]" />
        approved {year ?? ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-2)]">
      <Sparkles size={10} />
      novel candidate
    </span>
  );
}

/* ---------------------------- Score bars + rank ----------------------- */
function ScoreBar({
  label, value, accent, signedScore,
}: {
  label: string;
  value: number;
  accent?: boolean;
  signedScore?: boolean;
}) {
  // Model scores are negative distances (closer to 0 = better).
  // Graph scores are [0,1] Jaccard. Fused scores are tiny RRF values.
  const display = label === "fused" ? value.toFixed(4) : value.toFixed(3);
  const bar = signedScore
    ? Math.max(0, Math.min(1, 1 + value))           // -1..0 -> 0..1
    : Math.max(0, Math.min(1, label === "fused" ? value * 30 : value));

  return (
    <div className="tilt rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          {label}
        </span>
        <span className="font-mono tabular text-[14px] text-[var(--color-fg-0)]">{display}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-3)]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(bar * 100)}%` }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className={cn("h-full", accent ? "bg-[var(--color-acc)]" : "bg-[var(--color-fg-2)]")}
        />
      </div>
    </div>
  );
}

function RankBox({ rank, graphRank }: { rank: number; graphRank: number }) {
  return (
    <div className="tilt rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)]">
          rank
        </span>
        <span className="font-mono tabular text-[14px] text-[var(--color-fg-0)]">#{rank}</span>
      </div>
      <div className="mt-2 font-mono text-[10px] text-[var(--color-fg-3)]">
        model #{rank} · graph #{graphRank}
      </div>
    </div>
  );
}

/* ---------------------------- Model chip group ------------------------- */
const ALL_MODELS: ModelName[] = ["rotate", "rgcn", "compgcn"];

function ModelChipGroup({
  available,
  selected,
  onSelect,
}: {
  available: ModelName[];
  selected: ModelName;
  onSelect: (m: ModelName) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ALL_MODELS.map((m) => {
        const isAvailable = available.includes(m);
        const isActive = selected === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => isAvailable && onSelect(m)}
            disabled={!isAvailable}
            title={
              isAvailable
                ? `Score with ${modelLabel(m)}`
                : `${modelLabel(m)} not loaded in this deploy — re-train via scripts/colab_gnn_training.ipynb to enable.`
            }
            className={cn(
              "lift rounded-md border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors",
              isActive
                ? "border-[var(--color-acc)]/60 bg-[var(--color-acc)]/15 text-[var(--color-acc)]"
                : isAvailable
                  ? "border-[var(--color-line-2)] bg-[var(--color-bg-2)] text-[var(--color-fg-1)] hover:border-[var(--color-acc)]/40 hover:text-[var(--color-fg-0)]"
                  : "cursor-not-allowed border-dashed border-[var(--color-line)] bg-transparent text-[var(--color-fg-3)] opacity-60",
            )}
          >
            {modelLabel(m)}
            {!isAvailable && <span className="ml-1 text-[9px] opacity-70">— pending</span>}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------- Section header ---------------------------- */
function SectionHeader({ eyebrow, title, sub }: { eyebrow: string; title: string; sub: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="max-w-[760px]"
    >
      <div className="font-mono uppercase tracking-[0.18em] text-[var(--color-acc)]" style={{ fontSize: 'var(--fs-eyebrow)' }}>
        {eyebrow}
      </div>
      <h2 className="mt-3 font-display font-semibold leading-[1.1] tracking-[-0.015em] text-[var(--color-fg-0)]" style={{ fontSize: 'var(--fs-h2)' }}>
        {title}
      </h2>
      <p className="mt-3 text-pretty text-[var(--color-fg-2)]" style={{ fontSize: 'var(--fs-body)' }}>{sub}</p>
    </motion.div>
  );
}
