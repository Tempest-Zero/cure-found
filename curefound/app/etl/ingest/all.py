"""
Run all Phase 1 ingestors in dependency order and write the merged KG.

Usage
-----
    python -m app.etl.ingest.all                   # all enabled sources
    python -m app.etl.ingest.all --source primekg  # single source only
    python -m app.etl.ingest.all --dry-run         # print plan, don't ingest
    python -m app.etl.ingest.all --target neo4j    # write to Neo4j
    python -m app.etl.ingest.all --target json     # write to seed KG JSON (default)

Ingestor dependency order
-------------------------
1. hpo      — symptom nodes (referenced by orphanet + primekg phenotype edges)
2. orphanet — disease names + ORPHA IDs (enriches PrimeKG disease nodes)
3. reactome — pathway nodes (referenced by PrimeKG PARTICIPATES_IN edges)
4. primekg  — backbone graph (references hpo/reactome/orphanet nodes)
5. drugcentral — authoritative TREATS edges (overwrites PrimeKG TREATS)

Output (--target json): data/seed/kg.json (in-place update)
Output (--target neo4j): writes nodes+edges via Bolt to the configured DB
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.etl._base import IngestionOutput, KGAccumulator

_log = get_logger(__name__)

# Ingestor registry — order matters (see docstring)
_INGESTOR_ORDER = ["hpo", "orphanet", "reactome", "primekg", "drugcentral"]

_INGESTOR_CLASSES = {
    "hpo": "app.etl.ingest.hpo:HPOIngestor",
    "orphanet": "app.etl.ingest.orphanet:OrphanetIngestor",
    "reactome": "app.etl.ingest.reactome:ReactomeIngestor",
    "primekg": "app.etl.ingest.primekg:PrimeKGIngestor",
    "drugcentral": "app.etl.ingest.drugcentral:DrugCentralIngestor",
}

_ENABLE_FLAG = {
    "hpo": "INGEST_HPO",
    "orphanet": "INGEST_ORPHANET",
    "reactome": "INGEST_REACTOME",
    "primekg": "INGEST_PRIMEKG",
    "drugcentral": "INGEST_DRUGCENTRAL",
}


def _load_ingestor(name: str):  # type: ignore[return]
    module_path, class_name = _INGESTOR_CLASSES[name].split(":")
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)()


def run_ingestors(
    settings: Settings,
    *,
    only: str | None = None,
    dry_run: bool = False,
) -> IngestionOutput:
    """Execute ingestors in order, merging outputs into a single KGAccumulator."""
    sources = [only] if only else _INGESTOR_ORDER
    master_acc = KGAccumulator()

    for name in sources:
        enable_flag = _ENABLE_FLAG.get(name, "")
        if enable_flag and not getattr(settings, enable_flag, True):
            _log.info("ingest.source_disabled", source=name)
            continue

        _log.info("ingest.source_start", source=name)
        if dry_run:
            _log.info("ingest.dry_run", source=name)
            continue

        try:
            ingestor = _load_ingestor(name)
            t0 = time.monotonic()
            output = ingestor.run(settings)
            elapsed = time.monotonic() - t0
            master_acc.add_nodes(output.nodes)
            master_acc.add_edges(output.edges, priority=ingestor.priority)
            _log.info(
                "ingest.source_done",
                source=name,
                n_nodes=len(output.nodes),
                n_edges=len(output.edges),
                elapsed_s=round(elapsed, 1),
            )
        except FileNotFoundError as exc:
            _log.warning(
                "ingest.source_skipped_missing_files",
                source=name,
                error=str(exc),
            )
        except Exception as exc:
            _log.error("ingest.source_failed", source=name, error=str(exc))
            raise

    _log.info(
        "ingest.merge_done",
        total_nodes=master_acc.n_nodes,
        total_edges=master_acc.n_edges,
    )
    out = master_acc.to_output()
    return IngestionOutput(nodes=out["nodes"], edges=out["edges"])


def write_json(output: IngestionOutput, dest: Path, version: str) -> None:
    """Write the merged KG to a JSON file (same format as data/seed/kg.json)."""
    payload: dict[str, Any] = {
        "version": version,
        "nodes": output.nodes,
        "edges": output.edges,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _log.info(
        "ingest.json_written",
        path=str(dest),
        n_nodes=len(output.nodes),
        n_edges=len(output.edges),
    )


def write_neo4j(output: IngestionOutput, settings: Settings) -> None:
    """Write the merged KG to Neo4j via Bolt using batched MERGE queries."""
    try:
        from neo4j import GraphDatabase  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "neo4j Python driver not installed. "
            "Run `pip install 'neo4j>=5'` or use --target json."
        ) from exc

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    _log.info("ingest.neo4j_connect", uri=settings.NEO4J_URI)
    driver.verify_connectivity()

    # Apply schema (constraints + indexes) from init.cypher if it exists
    _apply_schema(driver, settings)

    # Write nodes in batches of 500
    _batch_write_nodes(driver, output.nodes, settings.NEO4J_DATABASE, batch_size=500)
    # Write edges in batches of 500
    _batch_write_edges(driver, output.edges, settings.NEO4J_DATABASE, batch_size=500)

    # Write metadata node for version tracking
    with driver.session(database=settings.NEO4J_DATABASE) as sess:
        import time as _time

        sess.run(
            "MERGE (m:_Meta {key: 'kg'}) "
            "SET m.version = $version, m.updated_at = $ts",
            version=f"primekg-phase1-{int(_time.time())}",
            ts=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        )

    driver.close()
    _log.info("ingest.neo4j_done", n_nodes=len(output.nodes), n_edges=len(output.edges))


def _apply_schema(driver: Any, settings: Settings) -> None:
    """Execute docker/neo4j/init.cypher against the DB if the file exists."""
    from app.core.paths import PROJECT_ROOT

    init_path = PROJECT_ROOT / "docker" / "neo4j" / "init.cypher"
    if not init_path.exists():
        return
    cypher_text = init_path.read_text(encoding="utf-8")
    # Strip comments and split on semicolons
    statements = [
        stmt.strip()
        for stmt in cypher_text.split(";")
        if stmt.strip() and not stmt.strip().startswith("//")
    ]
    _log.info("ingest.applying_schema", n_statements=len(statements))
    with driver.session(database=settings.NEO4J_DATABASE) as sess:
        for stmt in statements:
            if stmt:
                try:
                    sess.run(stmt)
                except Exception as exc:
                    # Schema statements are idempotent (IF NOT EXISTS); log and continue
                    _log.warning("ingest.schema_stmt_failed", stmt=stmt[:80], error=str(exc))


def _batch_write_nodes(
    driver: Any, nodes: list[dict], database: str, batch_size: int = 500
) -> None:
    _log.info("ingest.writing_nodes", n=len(nodes))
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i : i + batch_size]
        with driver.session(database=database) as sess:
            sess.run(
                """
                UNWIND $batch AS node
                MERGE (n {id: node.id})
                SET n += node.props, n:_Node
                WITH n, node
                CALL apoc.create.addLabels(n, [node.node_type]) YIELD node AS _
                RETURN count(*)
                """,
                batch=[
                    {
                        "id": n["id"],
                        "node_type": n.get("type", "Unknown"),
                        "props": {
                            k: v
                            for k, v in n.items()
                            if k not in ("type", "xrefs")
                            and v is not None
                        }
                        | (n.get("xrefs") or {}),
                    }
                    for n in batch
                ],
            )
    _log.info("ingest.nodes_written", n=len(nodes))


def _batch_write_edges(
    driver: Any, edges: list[dict], database: str, batch_size: int = 500
) -> None:
    _log.info("ingest.writing_edges", n=len(edges))
    # Group edges by relation type (each rel requires a different MERGE template)
    from collections import defaultdict

    by_rel: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        by_rel[e["rel"]].append(e)

    for rel, rel_edges in by_rel.items():
        for i in range(0, len(rel_edges), batch_size):
            batch = rel_edges[i : i + batch_size]
            with driver.session(database=database) as sess:
                sess.run(
                    f"""
                    UNWIND $batch AS e
                    MATCH (h {{id: e.head}})
                    MATCH (t {{id: e.tail}})
                    MERGE (h)-[r:`{rel}`]->(t)
                    SET r += e.props
                    """,
                    batch=[
                        {
                            "head": e["head"],
                            "tail": e["tail"],
                            "props": {
                                k: v
                                for k, v in e.items()
                                if k not in ("head", "rel", "tail") and v is not None
                            },
                        }
                        for e in batch
                    ],
                )
    _log.info("ingest.edges_written", n=len(edges))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.etl.ingest.all",
        description="Run Phase 1 ingestors and write the merged KG.",
    )
    p.add_argument("--source", metavar="NAME", help="Run only this ingestor")
    p.add_argument(
        "--target",
        choices=["json", "neo4j"],
        default="json",
        help="Output target: json (default) or neo4j",
    )
    p.add_argument("--dry-run", action="store_true", help="Show plan without running")
    p.add_argument(
        "--output",
        metavar="PATH",
        help="Destination JSON path (default: data/seed/kg.json)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()

    output = run_ingestors(settings, only=args.source, dry_run=args.dry_run)

    if args.dry_run:
        _log.info("ingest.dry_run_complete")
        return

    if not output.nodes:
        _log.warning("ingest.no_output", hint="Check that raw data files are present.")
        sys.exit(1)

    if args.target == "neo4j":
        write_neo4j(output, settings)
    else:
        dest = Path(args.output) if args.output else settings.seed_kg_path
        import time as _time

        version = f"phase1-{_time.strftime('%Y%m%d')}"
        write_json(output, dest, version=version)


if __name__ == "__main__":
    main()
