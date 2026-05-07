import { useEffect, useState } from "react";
import { CircleDot, WifiOff } from "lucide-react";
import { checkApiStatus, type ApiState } from "@/lib/utils";

/**
 * A small chip that visually advertises whether the data on screen came
 * from the live FastAPI backend or from a static fallback bundled with
 * the SPA. This is deliberately prominent — the whole point is to make
 * "is this hitting the real model?" visually unambiguous.
 *
 * Three states:
 *   - checking : neutral dot + "checking"
 *   - live     : green pulsing dot + "live · {sourceLabel}"
 *   - offline  : amber wifi-off + "cached fallback"
 *
 * Pass `lastRequestState` to override the chip after a specific call
 * succeeded or failed (so it reflects the latest user action, not just
 * the startup health-check).
 */
export function ApiStatusChip({
  sourceLabel = "RotatE",
  lastRequestState,
  className,
}: {
  sourceLabel?: string;
  lastRequestState?: "live" | "offline" | null;
  className?: string;
}) {
  const [state, setState] = useState<ApiState>("checking");

  useEffect(() => {
    let alive = true;
    checkApiStatus().then((s) => {
      if (alive) setState(s);
    });
    const id = setInterval(async () => {
      const s = await checkApiStatus(true);
      if (alive) setState(s);
    }, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // If a recent request told us it actually came from fallback, override the
  // health-check optimism. Conversely, a successful live response upgrades us.
  const effective: ApiState =
    lastRequestState === "offline"
      ? "offline"
      : lastRequestState === "live"
        ? "live"
        : state;

  if (effective === "checking") {
    return (
      <span
        className={
          "inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-3)] " +
          (className ?? "")
        }
      >
        <CircleDot size={10} className="animate-pulse" />
        checking
      </span>
    );
  }

  if (effective === "live") {
    return (
      <span
        className={
          "inline-flex items-center gap-1.5 rounded-full border border-[var(--color-acc)]/40 bg-[var(--color-acc)]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-acc)] " +
          (className ?? "")
        }
        title="Hitting the real FastAPI backend with live model inference."
      >
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-acc)] opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--color-acc)]" />
        </span>
        live · {sourceLabel}
      </span>
    );
  }

  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-warn)] " +
        (className ?? "")
      }
      title="Backend unreachable — showing static fallback so the UI stays demo-able."
    >
      <WifiOff size={10} />
      offline · fallback
    </span>
  );
}
