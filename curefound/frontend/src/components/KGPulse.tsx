/**
 * KGPulse — branded loading indicator shaped like a mini knowledge graph.
 * Pure SVG with SMIL animations — no JS runtime cost.
 * Replaces the generic Loader2 spinning icon across Repurpose + Diagnose.
 */
export function KGPulse({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="3" fill="currentColor">
        <animate attributeName="r" values="3;5;3" dur="1.2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0.4;1" dur="1.2s" repeatCount="indefinite" />
      </circle>
      <circle cx="4" cy="6" r="1.4" fill="currentColor" opacity="0.6">
        <animate attributeName="opacity" values="0.6;0.15;0.6" dur="1.2s" begin="0.1s" repeatCount="indefinite" />
      </circle>
      <circle cx="20" cy="6" r="1.4" fill="currentColor" opacity="0.6">
        <animate attributeName="opacity" values="0.6;0.15;0.6" dur="1.2s" begin="0.3s" repeatCount="indefinite" />
      </circle>
      <circle cx="4" cy="18" r="1.4" fill="currentColor" opacity="0.6">
        <animate attributeName="opacity" values="0.6;0.15;0.6" dur="1.2s" begin="0.5s" repeatCount="indefinite" />
      </circle>
      <circle cx="20" cy="18" r="1.4" fill="currentColor" opacity="0.6">
        <animate attributeName="opacity" values="0.6;0.15;0.6" dur="1.2s" begin="0.7s" repeatCount="indefinite" />
      </circle>
      {/* Faint connecting lines */}
      <line x1="12" y1="12" x2="4" y2="6" stroke="currentColor" strokeWidth="0.5" opacity="0.2" />
      <line x1="12" y1="12" x2="20" y2="6" stroke="currentColor" strokeWidth="0.5" opacity="0.2" />
      <line x1="12" y1="12" x2="4" y2="18" stroke="currentColor" strokeWidth="0.5" opacity="0.2" />
      <line x1="12" y1="12" x2="20" y2="18" stroke="currentColor" strokeWidth="0.5" opacity="0.2" />
    </svg>
  );
}
