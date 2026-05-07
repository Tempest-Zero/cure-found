import { Github, ShieldAlert } from "lucide-react";

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-line)] bg-[var(--color-bg-1)]">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="font-display text-[14px] font-semibold tracking-tight">CureFound</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-2 py-0.5 font-mono text-[10px] text-[var(--color-fg-2)]">
            <ShieldAlert size={11} className="text-[var(--color-warn)]" />
            Research prototype · Not for clinical use
          </span>
        </div>
        <div className="flex items-center gap-5 font-mono text-[12px] text-[var(--color-fg-3)]">
          <a href="#methods" className="hover:text-[var(--color-fg-1)]">Methods</a>
          <a href="#eval" className="hover:text-[var(--color-fg-1)]">Eval</a>
          <a href="/docs" target="_blank" rel="noreferrer" className="hover:text-[var(--color-fg-1)]">
            OpenAPI
          </a>
          <a
            href="https://github.com/Tempest-Zero/cure-found"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 hover:text-[var(--color-fg-1)]"
          >
            <Github size={12} /> Code
          </a>
        </div>
      </div>
    </footer>
  );
}
