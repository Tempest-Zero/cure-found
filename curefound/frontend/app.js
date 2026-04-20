// CureFound MVP frontend.
// Vanilla JS + Cytoscape.js via CDN (no build step).

const API = ""; // same origin

const TYPE_COLORS = {
  Disease: "#e86a7a", Gene: "#e3b262", Protein: "#c48be3",
  Drug: "#5b8dee", Pathway: "#4ecb8d", Symptom: "#6ac7d9",
};

// ---------------- helpers ---------------- //
async function apiGet(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
  return r.json();
}
async function apiPost(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
  return r.json();
}

function debounce(fn, ms=200) {
  let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "onclick") e.addEventListener("click", v);
    else if (k === "onchange") e.addEventListener("change", v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    e.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

// ---------------- tabs ---------------- //
document.querySelectorAll("nav .tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav .tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll("main .panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const id = "panel-" + btn.dataset.tab;
    document.getElementById(id).classList.add("active");
  });
});

// ---------------- stats header ---------------- //
apiGet("/stats").then(s => {
  document.getElementById("stats").textContent =
    `KG ${s.kg_version} · ${s.n_entities} entities · ${s.n_relations} relations · ${s.n_triples} triples`;
});

// ---------------- shared autocomplete ---------------- //
function wireSearch(inputId, suggestId, typeFilter, onPick) {
  const input = document.getElementById(inputId);
  const box   = document.getElementById(suggestId);
  const runSearch = debounce(async () => {
    const q = input.value.trim();
    if (!q) { box.classList.remove("show"); box.innerHTML = ""; return; }
    const params = new URLSearchParams({ q, limit: "12" });
    if (typeFilter) params.set("type", typeFilter);
    const items = await apiGet(`/search?${params}`);
    box.innerHTML = "";
    if (items.length === 0) { box.classList.remove("show"); return; }
    items.forEach(it => {
      const row = el("div", { class: "item",
        onclick: () => { onPick(it); box.classList.remove("show"); }
      },
        el("span", {}, it.name),
        el("span", { class: "type" }, it.type)
      );
      box.appendChild(row);
    });
    box.classList.add("show");
  }, 150);
  input.addEventListener("input", runSearch);
  input.addEventListener("blur",  () => setTimeout(() => box.classList.remove("show"), 200));
  input.addEventListener("focus", runSearch);
}

// ---------------- Cytoscape rendering ---------------- //
function makeCy(container, elements) {
  return cytoscape({
    container,
    elements,
    style: [
      { selector: "node",
        style: {
          "background-color": (e) => TYPE_COLORS[e.data("type")] || "#888",
          "label": "data(label)",
          "color": "#e6e8ef",
          "font-size": 10,
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": 4,
          "text-wrap": "wrap",
          "text-max-width": 90,
          "width": 22, "height": 22,
          "border-width": 1.5,
          "border-color": "#1f2638",
        }
      },
      { selector: "node:selected",
        style: { "border-color": "#fff", "border-width": 3 } },
      { selector: "edge",
        style: {
          "width": 1.2,
          "line-color": "#2a3249",
          "target-arrow-color": "#2a3249",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "label": "data(label)",
          "font-size": 8,
          "color": "#8892a7",
          "text-background-color": "#0b0f1a",
          "text-background-opacity": 0.6,
          "text-background-padding": 1,
        }
      },
      { selector: 'edge[label = "TREATS"]',
        style: { "line-color": "#4ecb8d", "target-arrow-color": "#4ecb8d", "width": 2 } },
      { selector: 'edge[label = "CAUSES"]',
        style: { "line-color": "#e86a7a", "target-arrow-color": "#e86a7a", "width": 2 } },
    ],
    layout: { name: "cose", animate: false, padding: 20, idealEdgeLength: 90, nodeRepulsion: 5000 },
  });
}

async function renderSubgraphInto(containerId, nodeId, k=2, maxNodes=80) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const g = await apiGet(`/subgraph?node_id=${encodeURIComponent(nodeId)}&k=${k}&max_nodes=${maxNodes}`);
  const elements = [
    ...g.nodes,
    ...g.edges,
  ];
  const cy = makeCy(container, elements);
  // highlight the queried node
  const target = cy.$(`node[id = "${nodeId}"]`);
  target.style({ "background-color": "#ffffff", "border-color": "#ffffff", "border-width": 3, "width": 28, "height": 28 });
  return cy;
}

// ---------------- Repurpose tab ---------------- //
const repState = { disease: null, candidates: [], selectedIdx: -1 };

wireSearch("rep-search", "rep-suggest", "Disease", (item) => {
  repState.disease = item;
  document.getElementById("rep-search").value = item.name;
  runRepurpose();
});

document.getElementById("rep-run").addEventListener("click", runRepurpose);

async function runRepurpose() {
  if (!repState.disease) {
    alert("Pick a disease from the suggestions first.");
    return;
  }
  const topk = parseInt(document.getElementById("rep-topk").value) || 10;
  const inc  = document.getElementById("rep-include-approved").checked;
  document.getElementById("rep-title").textContent = `Ranked repurposing candidates for ${repState.disease.name}`;
  const resp = await apiPost("/repurpose", {
    disease_id: repState.disease.id, top_k: topk, include_already_approved: inc,
  });
  repState.candidates = resp.candidates;
  repState.selectedIdx = -1;
  renderRepResults();
  // default: render KG neighborhood of the disease
  document.getElementById("rep-graph-title").textContent = `2-hop neighborhood of ${resp.disease_name}`;
  renderSubgraphInto("rep-graph", resp.disease_id, 2, 80);
}

function renderRepResults() {
  const list = document.getElementById("rep-results");
  list.innerHTML = "";
  repState.candidates.forEach((c, i) => {
    const li = el("li", {
      class: i === repState.selectedIdx ? "selected" : "",
      onclick: () => selectRepCandidate(i),
    },
      el("div", { class: "row1" },
        el("span", { class: "name" }, c.drug_name),
        el("span", { class: "score" }, `rrf=${c.fused_score.toFixed(4)}  m=${c.model_score.toFixed(2)}  g=${c.graph_score.toFixed(2)}`)
      ),
      el("div", { class: "row2" },
        `#${c.model_rank} by model, #${c.graph_rank} by pathway-overlap`,
        c.already_approved ? el("span", { class: "badge approved" }, `approved ${c.approval_year || ""}`) : null
      ),
      c.evidence_paths && c.evidence_paths[0]
        ? el("div", { class: "path" }, renderPath(c.evidence_paths[0]))
        : null
    );
    list.appendChild(li);
  });
  if (repState.candidates.length === 0) {
    list.innerHTML = '<li style="padding: 20px; color: var(--muted);">No candidates — try enabling "include already-approved" or pick another disease.</li>';
  }
}

function renderPath(path) {
  if (!path || path.length === 0) return "";
  const parts = [];
  for (const e of path) {
    parts.push(`[${e.rel}] ${e.to.split(":")[1] || e.to}`);
  }
  return "via " + parts.join(" -> ");
}

async function selectRepCandidate(i) {
  repState.selectedIdx = i;
  renderRepResults();
  const c = repState.candidates[i];
  document.getElementById("rep-graph-title").textContent = `Evidence: ${c.drug_name} ↔ ${repState.disease.name}`;
  // Render subgraph that includes both the drug and the disease
  const g1 = await apiGet(`/subgraph?node_id=${c.drug_id}&k=2&max_nodes=40`);
  const g2 = await apiGet(`/subgraph?node_id=${repState.disease.id}&k=2&max_nodes=40`);
  const nodeIds = new Set();
  const nodes = [];
  const edges = [];
  [...g1.nodes, ...g2.nodes].forEach(n => {
    if (!nodeIds.has(n.data.id)) { nodeIds.add(n.data.id); nodes.push(n); }
  });
  const edgeIds = new Set();
  [...g1.edges, ...g2.edges].forEach(e => {
    if (!edgeIds.has(e.data.id)) { edgeIds.add(e.data.id); edges.push(e); }
  });
  const container = document.getElementById("rep-graph");
  container.innerHTML = "";
  const cy = makeCy(container, [...nodes, ...edges]);
  // highlight drug (green border) and disease (red border)
  cy.$(`node[id = "${c.drug_id}"]`).style({ "border-color": "#4ecb8d", "border-width": 3, "width": 28, "height": 28 });
  cy.$(`node[id = "${repState.disease.id}"]`).style({ "border-color": "#e86a7a", "border-width": 3, "width": 28, "height": 28 });
}

// ---------------- Diagnose tab ---------------- //
const diagState = { symptoms: new Map() }; // id -> {id, name, hpo_id}

function renderDiagChips() {
  const host = document.getElementById("diag-chips");
  host.innerHTML = "";
  if (diagState.symptoms.size === 0) {
    host.appendChild(el("span", { class: "empty" }, "Add symptoms above, or pick a preset."));
    return;
  }
  diagState.symptoms.forEach(s => {
    host.appendChild(el("div", { class: "chip" },
      s.name,
      el("span", { class: "x", onclick: () => { diagState.symptoms.delete(s.id); renderDiagChips(); } }, "×")
    ));
  });
}
renderDiagChips();

wireSearch("diag-search", "diag-suggest", "Symptom", (item) => {
  diagState.symptoms.set(item.id, { id: item.id, name: item.name, hpo_id: item.xrefs ? item.xrefs.hpo_id : null });
  document.getElementById("diag-search").value = "";
  renderDiagChips();
});

document.querySelectorAll(".preset").forEach(btn => {
  btn.addEventListener("click", async () => {
    diagState.symptoms.clear();
    const ids = btn.dataset.ids.split(",");
    // resolve each HPO id to a node via /search (cheap; 4–6 calls)
    for (const hpo of ids) {
      // direct lookup via search: we store hpo_id in xrefs; search is name-based, so we cheat via a separate endpoint.
      // simpler: just add chip with label="HP:xxx" and resolve server-side on /diagnose.
      diagState.symptoms.set(hpo, { id: hpo, name: hpo, hpo_id: hpo });
    }
    renderDiagChips();
    runDiagnose();
  });
});

document.getElementById("diag-clear").addEventListener("click", () => {
  diagState.symptoms.clear(); renderDiagChips();
  document.getElementById("diag-results").innerHTML = "";
  document.getElementById("diag-graph").innerHTML = "";
});

document.getElementById("diag-run").addEventListener("click", runDiagnose);

async function runDiagnose() {
  const ids = [...diagState.symptoms.keys()];
  if (ids.length === 0) { alert("Add at least one symptom."); return; }
  const topk = parseInt(document.getElementById("diag-topk").value) || 10;
  const resp = await apiPost("/diagnose", { symptoms: ids, top_k: topk });
  // After resolution, the chips might have canonical ids; re-sync
  const list = document.getElementById("diag-results");
  list.innerHTML = "";
  resp.candidates.forEach((c, i) => {
    const li = el("li", {
      onclick: () => selectDiagCandidate(c),
    },
      el("div", { class: "row1" },
        el("span", { class: "name" }, c.disease_name),
        el("span", { class: "score" }, `rrf=${c.fused_score.toFixed(4)}  jac=${c.jaccard_score.toFixed(2)}  idf=${c.idf_score.toFixed(1)}`)
      ),
      el("div", { class: "row2" },
        c.is_rare ? el("span", { class: "badge rare" }, "rare") : null
      ),
      c.matched_symptoms.length
        ? el("div", { class: "match-row" }, "matched: " + c.matched_symptoms.map(s => s.name).join(", "))
        : null,
      c.missing_symptoms.length
        ? el("div", { class: "miss-row" }, "not in input: " + c.missing_symptoms.slice(0, 5).map(s => s.name).join(", ") + (c.missing_symptoms.length > 5 ? "…" : ""))
        : null
    );
    list.appendChild(li);
  });
  if (resp.candidates.length === 0) {
    list.innerHTML = '<li style="padding: 20px; color: var(--muted);">No matches. Check that your HPO ids are in-KG.</li>';
  }
}

async function selectDiagCandidate(c) {
  document.getElementById("diag-graph-title").textContent = `KG neighborhood of ${c.disease_name}`;
  renderSubgraphInto("diag-graph", c.disease_id, 2, 80);
}

// ---------------- Explore tab ---------------- //
wireSearch("exp-search", "exp-suggest", null, async (item) => {
  document.getElementById("exp-search").value = item.name;
  const k = parseInt(document.getElementById("exp-k").value) || 2;
  const mx = parseInt(document.getElementById("exp-max").value) || 80;
  const detail = await apiGet(`/node/${encodeURIComponent(item.id)}`);
  const info = document.getElementById("exp-node-info");
  info.innerHTML = "";
  info.appendChild(el("strong", {}, item.name));
  info.append(` (${item.type}) — `);
  info.append(`in-degree ${detail.in_degree}, out-degree ${detail.out_degree}`);
  if (detail.xrefs) {
    const xrefStr = Object.entries(detail.xrefs).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join("  ·  ");
    if (xrefStr) info.appendChild(el("div", { style: "margin-top:4px;" }, xrefStr));
  }
  renderSubgraphInto("exp-graph", item.id, k, mx);
});
