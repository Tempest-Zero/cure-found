// ============================================================================
// CureFound — Neo4j schema initialisation (Phase 1)
//
// This file is mounted read-only at:
//   /var/lib/neo4j/conf/import/init.cypher
//
// It is applied at startup by the admin ingest bootstrap script
// (app/etl/ingest/neo4j_init.py) which runs `neo4j-admin` or
// executes this via the Bolt driver before any ingest begins.
//
// Design notes:
//   - Uniqueness constraints create backing indexes automatically in Neo4j 5.
//   - `id` is the canonical CureFound identifier (e.g. "D:NPC", "DR:IMIGLUCERASE").
//   - External-id xref indexes (MONDO, HPO, HGNC) are regular btree indexes
//     because they are not unique per-node (one disease can map to several
//     external identifiers stored in a list property).
//   - Relation-type indexes are added where the ingestor is expected to do
//     large pattern scans (e.g. `MATCH ()-[r:TREATS]-()` on startup to
//     populate the treats_edge cache).
//
// Phase 1 constraint / index plan — more added as ingestors land.
// ============================================================================

// --------------------------------------------------------------------------
// Node uniqueness constraints (one per label that uses a canonical `id`)
// --------------------------------------------------------------------------

CREATE CONSTRAINT disease_id_unique IF NOT EXISTS
  FOR (d:Disease) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT drug_id_unique IF NOT EXISTS
  FOR (dr:Drug) REQUIRE dr.id IS UNIQUE;

CREATE CONSTRAINT symptom_id_unique IF NOT EXISTS
  FOR (s:Symptom) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT gene_id_unique IF NOT EXISTS
  FOR (g:Gene) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT pathway_id_unique IF NOT EXISTS
  FOR (p:Pathway) REQUIRE p.id IS UNIQUE;

// --------------------------------------------------------------------------
// xref lookup indexes (external id cross-references stored as node props)
// --------------------------------------------------------------------------

CREATE INDEX disease_mondo_idx IF NOT EXISTS
  FOR (d:Disease) ON (d.mondo_id);

CREATE INDEX disease_omim_idx IF NOT EXISTS
  FOR (d:Disease) ON (d.omim_id);

CREATE INDEX disease_orphanet_idx IF NOT EXISTS
  FOR (d:Disease) ON (d.orphanet_id);

CREATE INDEX symptom_hpo_idx IF NOT EXISTS
  FOR (s:Symptom) ON (s.hpo_id);

CREATE INDEX gene_hgnc_idx IF NOT EXISTS
  FOR (g:Gene) ON (g.hgnc_id);

CREATE INDEX gene_uniprot_idx IF NOT EXISTS
  FOR (g:Gene) ON (g.uniprot_id);

CREATE INDEX gene_entrez_idx IF NOT EXISTS
  FOR (g:Gene) ON (g.entrez_id);

CREATE INDEX drug_chembl_idx IF NOT EXISTS
  FOR (dr:Drug) ON (dr.chembl_id);

CREATE INDEX drug_drugbank_idx IF NOT EXISTS
  FOR (dr:Drug) ON (dr.drugbank_id);

// --------------------------------------------------------------------------
// Full-text search index — used by /search endpoint
// --------------------------------------------------------------------------

CREATE FULLTEXT INDEX entity_name_fts IF NOT EXISTS
  FOR (n:Disease|Drug|Symptom|Gene|Pathway)
  ON EACH [n.name, n.synonyms];

// --------------------------------------------------------------------------
// Relationship indexes
// --------------------------------------------------------------------------

// Fast lookup of all TREATS edges (approval_year filter for time-splits).
CREATE INDEX treats_approval_year_idx IF NOT EXISTS
  FOR ()-[r:TREATS]-() ON (r.approval_year);
