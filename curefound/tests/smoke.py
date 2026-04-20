"""End-to-end smoke test — no external server needed (uses FastAPI TestClient).
Exits non-zero if any check fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.main import app


def assert_eq(name, a, b):
    if a != b:
        print(f"FAIL {name}: expected {b}, got {a}"); sys.exit(1)
    print(f"ok   {name}")


def assert_true(name, cond, detail=""):
    if not cond:
        print(f"FAIL {name}: {detail}"); sys.exit(1)
    print(f"ok   {name}")


def main() -> None:
    c = TestClient(app)

    # 1. health
    h = c.get("/health").json()
    assert_eq("health.status", h["status"], "ok")

    # 2. stats: plausible node/edge counts
    s = c.get("/stats").json()
    assert_true("stats.n_entities>=80",  s["n_entities"] >= 80,  f"got {s['n_entities']}")
    assert_true("stats.n_triples>=100",  s["n_triples"]  >= 100, f"got {s['n_triples']}")
    assert_true("stats has TREATS",      "TREATS" in s["by_rel_type"])
    assert_true("stats has Disease",     "Disease" in s["by_node_type"])

    # 3. search: "niem" returns Niemann-Pick diseases
    r = c.get("/search?q=niem").json()
    names = [x["name"] for x in r]
    assert_true("search niem -> NPC hit",
                any("Niemann-Pick" in n for n in names),
                f"got {names}")

    # 4. node: D:NPC has xrefs
    n = c.get("/node/D:NPC").json()
    assert_eq("node D:NPC name", n["name"], "Niemann-Pick disease type C")
    assert_eq("node D:NPC mondo", n["xrefs"]["mondo_id"], "MONDO:0009937")

    # 5. repurpose: at least one candidate for NPC
    resp = c.post("/repurpose", json={"disease_id": "D:NPC", "top_k": 10,
                                       "include_already_approved": False}).json()
    assert_true("repurpose NPC has candidates",
                len(resp["candidates"]) >= 5,
                f"got {len(resp['candidates'])} candidates")
    cand_names = [c["drug_name"] for c in resp["candidates"]]
    # HP-β-CD or Vorinostat or Rapamycin are repurposing candidates we expect to surface
    known = any("cyclodextrin" in n.lower() or "vorinostat" in n.lower() or "rapamycin" in n.lower()
                for n in cand_names)
    assert_true("repurpose NPC surfaces a known repurposing candidate",
                known, f"candidates were {cand_names}")

    # 6. repurpose via MONDO id works
    resp2 = c.post("/repurpose", json={"disease_id": "MONDO:0009937", "top_k": 3,
                                        "include_already_approved": True}).json()
    assert_eq("repurpose MONDO->D:NPC", resp2["disease_id"], "D:NPC")

    # 7. diagnose: cherry-red spot + hypotonia + dev delay + seizures -> Tay-Sachs top
    d = c.post("/diagnose", json={
        "symptoms": ["HP:0010729", "HP:0001252", "HP:0001263", "HP:0001250"],
        "top_k": 5,
    }).json()
    assert_true("diagnose has candidates", len(d["candidates"]) >= 1)
    top = d["candidates"][0]["disease_name"]
    assert_eq("diagnose cherry-red+hypotonia+seizures+devdelay -> Tay-Sachs",
              top, "Tay-Sachs disease")

    # 8. diagnose: Fabry-typical symptoms -> Fabry top
    d = c.post("/diagnose", json={
        "symptoms": ["HP:0001073", "HP:0000077", "HP:0009830", "HP:0001638"],
        "top_k": 5,
    }).json()
    assert_eq("diagnose Fabry profile -> Fabry", d["candidates"][0]["disease_name"], "Fabry disease")

    # 9. subgraph around NPC
    sg = c.get("/subgraph?node_id=D:NPC&k=2&max_nodes=40").json()
    assert_true("subgraph NPC >= 10 nodes", len(sg["nodes"]) >= 10, f"got {len(sg['nodes'])}")
    assert_true("subgraph NPC has edges",   len(sg["edges"]) >= 5)

    # 10. frontend is served
    root = c.get("/")
    assert_true("frontend index loads", root.status_code == 200 and b"CureFound" in root.content)

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
