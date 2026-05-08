import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Where to send API requests.
 * - When the SPA is served from `/ui/...` (production/Docker), call relative.
 * - When running `vite dev` on :5173, point at the FastAPI dev server :8000.
 */
const API_BASE =
  typeof window !== "undefined" && window.location.pathname.startsWith("/ui")
    ? ""
    : "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/**
 * Live API status indicator. Sections call `useApiStatus()` once on mount
 * and display a green LIVE chip if the API responds, an amber OFFLINE chip
 * otherwise. This makes it visually unambiguous whether results are coming
 * from the real model or from cached fallback data.
 */
export type ApiState = "checking" | "live" | "offline";

let _statusCache: { state: ApiState; ts: number } | null = null;

export async function checkApiStatus(forceRefresh = false): Promise<ApiState> {
  const now = Date.now();
  if (!forceRefresh && _statusCache && now - _statusCache.ts < 30_000) {
    return _statusCache.state;
  }
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 3000);
    const r = await fetch(`${API_BASE}/health`, { signal: ctrl.signal });
    clearTimeout(t);
    const state: ApiState = r.ok ? "live" : "offline";
    _statusCache = { state, ts: now };
    return state;
  } catch {
    _statusCache = { state: "offline", ts: now };
    return "offline";
  }
}

/** Latency-style probe for /stats — used to surface KG version + entity count. */
export async function fetchStats(): Promise<{
  kg_version: string;
  n_entities: number;
  n_relations: number;
  n_triples: number;
} | null> {
  try {
    return await api("/stats");
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------------------------
 * Repurpose model selector — GET /repurpose/models returns the set of
 * scoring backends the live container has artifacts for. RotatE always
 * ships; R-GCN / CompGCN are present only if the matching .npz files were
 * bundled (Colab notebook produces them).
 * ------------------------------------------------------------------------- */

export type ModelName = "rotate" | "rgcn" | "compgcn";

const MODEL_LABELS: Record<ModelName, string> = {
  rotate: "RotatE",
  rgcn: "R-GCN",
  compgcn: "CompGCN",
};

export function modelLabel(m: ModelName): string {
  return MODEL_LABELS[m] ?? m;
}

/**
 * Cached fetch of available models. Falls back to ["rotate"] (the always-on
 * baseline) if the API is unreachable so the UI still renders a sensible chip.
 */
let _modelsCache: { models: ModelName[]; ts: number } | null = null;

export async function fetchAvailableModels(forceRefresh = false): Promise<ModelName[]> {
  const now = Date.now();
  if (!forceRefresh && _modelsCache && now - _modelsCache.ts < 60_000) {
    return _modelsCache.models;
  }
  try {
    const r = await api<{ models: string[] }>("/repurpose/models");
    const valid = r.models.filter((m): m is ModelName => m === "rotate" || m === "rgcn" || m === "compgcn");
    const models = valid.length > 0 ? valid : (["rotate"] as ModelName[]);
    _modelsCache = { models, ts: now };
    return models;
  } catch {
    const models: ModelName[] = ["rotate"];
    _modelsCache = { models, ts: now };
    return models;
  }
}
