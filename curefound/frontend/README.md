# CureFound — frontend

React 18 + Vite 5 + TypeScript + Tailwind v4 + Framer Motion + GSAP +
Cytoscape + Lucide. Aceternity-style components hand-ported (MIT) into
`src/components/aceternity/`.

## Stack

- **Vite 5** — dev server + production bundler.
- **React 18** strict mode, function components only.
- **TypeScript** strict, path alias `@/*` → `src/*`.
- **Tailwind v4** via `@tailwindcss/vite` — tokens declared inside
  `@theme` in `src/styles/index.css`.
- **Framer Motion** for state transitions, **GSAP** for the hero KG
  ambient drift.
- **Cytoscape.js** for the graph explorer (cose layout).
- **Lucide React** for all icons (no emoji).

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 — calls FastAPI at :8000
npm run build        # → frontend/dist/  (FastAPI mounts at /ui/*)
```

## Mount with FastAPI

Already wired. `app/core/paths.py` points `FRONTEND_DIR` at
`frontend/dist`, and `app/main.py` mounts that directory at `/ui` and
serves `/` → `frontend/dist/index.html`.

`vite.config.ts` sets `base: "/ui/"` so asset URLs resolve correctly
under the mount point.

The frontend auto-detects: when served from `/ui/...` it calls the API
at relative origin; when run via `vite dev` it points at
`http://localhost:8000`. See `src/lib/utils.ts → API_BASE`.

## API contract

Matches `app/repurpose/schemas.py` and `app/diagnose/schemas.py`
verbatim. Static fallbacks live in `src/lib/data.ts` — synthesised from
the real eval ranks in `data/artifacts/eval_report.json` — and kick in
whenever the API is unreachable, so the UI is always demo-able.

| Endpoint        | Method | Body                                                         |
|-----------------|--------|--------------------------------------------------------------|
| `/repurpose`    | POST   | `{ disease_id, top_k, include_already_approved }`            |
| `/diagnose`     | POST   | `{ symptoms: ["S:NAME" \| "HP:NNNNNNN"], top_k }`            |
| `/search`       | GET    | `?q=...&type=Disease&limit=20`                               |
| `/node/{id}`    | GET    | path = canonical or external id                              |
| `/subgraph`     | GET    | `?node_id=D:NPC&k=2&max_nodes=80`                            |
| `/stats`        | GET    | KG version + counts                                          |

## Structure

```
src/
├── App.tsx                          # Shell, NavBar, Hero
├── main.tsx
├── styles/index.css                 # Tailwind v4 + design tokens (@theme)
├── lib/
│   ├── data.ts                      # Real KG vocab + fallbacks + types
│   └── utils.ts                     # cn() + api()
└── components/
    ├── HeroKGCanvas.tsx             # GSAP-driven force layout, canvas
    ├── RepurposeSection.tsx         # /repurpose — input + ranked + evidence path
    ├── EvalSection.tsx              # RotatE vs TransE table + rank histogram
    ├── DiagnoseSection.tsx          # /diagnose — preset chips + symptoms + ranked
    ├── ExplorerSection.tsx          # Cytoscape full-KG explorer
    ├── MethodsSection.tsx           # Pipeline cards + math strip
    ├── Footer.tsx
    └── aceternity/index.tsx         # BackgroundBeams · Spotlight · MovingBorder · Card3D · AnimatedTooltip
```

## Design system (locked)

AI-Native UI + Minimalism + Dark Mode (OLED) + Swiss editorial. Tokens
declared once in `src/styles/index.css → @theme`.

- **Surfaces**: bg-0 `#0A0A0B`, bg-1 `#101013`, bg-2 `#17181B`, bg-3 `#1F2024`
- **Text**: fg-0 `#F0F1F4`, fg-1 `#E8E9EC`, fg-2 `#9398A1`, fg-3 `#6B7280`
- **Accent**: `#5EE38B` (bio-luminescent green) — used sparingly: primary
  CTA, focus, score-bar fills, hero status dot, matched-symptom chip
- **Type-coded entity colors** (Disease/Drug/Gene/Protein/Pathway/Symptom)
- **Type**: Inter Tight (display) / Inter (body) / JetBrains Mono
  (IDs · scores · relations · numbers always tabular)
- **Motion**: 150-250ms micro, 300-500ms reveals; `prefers-reduced-motion`
  honored globally + in GSAP guard
- **Anti-patterns avoided**: AI purple gradients, emoji icons,
  glassmorphism on data, decorative-only motion

## Skill checklist (pre-delivery)

- [x] No emojis as icons (Lucide everywhere)
- [x] Contrast >= 4.5:1 on all text/background pairs
- [x] Focus rings (`:focus-visible` token, 2px outline)
- [x] Touch targets >= 44x44 on mobile (CTAs, chips)
- [x] `prefers-reduced-motion` honored (global + GSAP guard)
- [x] One primary CTA per section
- [x] Semantic color tokens, no raw hex in components
- [x] Mobile-first, breakpoints 375/768/1024/1440
- [x] OG meta + theme-color for LinkedIn frame
- [x] "Research prototype. Not for clinical use." persistent in hero badge + footer
- [x] Real KG data + real eval numbers - no fabricated metrics
