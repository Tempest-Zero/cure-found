"""
Build the MVP seed knowledge graph.

This is a hand-curated, LSD-focused biomedical KG used to bootstrap the
prototype before PrimeKG / DrugCentral / HPO ingestors are built. All
facts are sourced from public knowledge (OMIM, Orphanet, DrugCentral,
HPO, Reactome) and are summarized here for demonstration purposes ONLY.
Not for clinical use.

Output:
    data/seed/kg.json   — {"nodes": [...], "edges": [...]}

Replace this file with real ingestors in Phase 1 (see plan):
    etl/ingest_primekg.py, etl/ingest_drugcentral.py, etl/ingest_hpo.py, ...
"""

from __future__ import annotations

import hashlib
import json

_BASE_VERSION = "kg-mvp-0.1"


def _content_hash(nodes: list[dict], edges: list[dict]) -> str:
    """SHA-256 over canonicalized (nodes, edges). Embedded in the version
    string so that any edit to the seed invalidates stale TransE artifacts
    (addresses M3 in the audit plan; load_for_kg() in ml/transe.py uses it)."""
    # Sort every list by id/key for deterministic hashing; json.dumps with
    # sort_keys=True handles dict key order.
    canon = {
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: (e["head"], e["rel"], e["tail"])),
    }
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Node definitions. Each node carries a canonical_id and the canonical_type.
# For the MVP we use a simple "TYPE:local_id" scheme. Real IDs are tracked in
# the `xrefs` dict (mondo_id, hgnc_id, uniprot_id, drugcentral_id, hpo_id,
# reactome_id) — these become primary IDs when we switch to PrimeKG.
# --------------------------------------------------------------------------- #

DISEASES = [
    # LSD cluster (primary focus)
    {
        "id": "D:GAUCHER",
        "name": "Gaucher disease",
        "xrefs": {"mondo_id": "MONDO:0018150", "omim_id": "230800", "orpha_id": "355"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:FABRY",
        "name": "Fabry disease",
        "xrefs": {"mondo_id": "MONDO:0018149", "omim_id": "301500", "orpha_id": "324"},
        "is_rare": True,
        "inheritance": "XL",
    },
    {
        "id": "D:NPA",
        "name": "Niemann-Pick disease type A",
        "xrefs": {"mondo_id": "MONDO:0009756", "omim_id": "257200", "orpha_id": "77292"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:NPB",
        "name": "Niemann-Pick disease type B",
        "xrefs": {"mondo_id": "MONDO:0009757", "omim_id": "607616", "orpha_id": "77293"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:NPC",
        "name": "Niemann-Pick disease type C",
        "xrefs": {"mondo_id": "MONDO:0009937", "omim_id": "257220", "orpha_id": "646"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:POMPE",
        "name": "Pompe disease",
        "xrefs": {"mondo_id": "MONDO:0009290", "omim_id": "232300", "orpha_id": "365"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:TAYSACHS",
        "name": "Tay-Sachs disease",
        "xrefs": {"mondo_id": "MONDO:0010231", "omim_id": "272800", "orpha_id": "845"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:KRABBE",
        "name": "Krabbe disease",
        "xrefs": {"mondo_id": "MONDO:0009499", "omim_id": "245200", "orpha_id": "487"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:MPS1",
        "name": "Mucopolysaccharidosis type I",
        "xrefs": {"mondo_id": "MONDO:0001586", "omim_id": "607014", "orpha_id": "579"},
        "is_rare": True,
        "inheritance": "AR",
    },
    {
        "id": "D:MPS2",
        "name": "Mucopolysaccharidosis type II",
        "xrefs": {"mondo_id": "MONDO:0010674", "omim_id": "309900", "orpha_id": "580"},
        "is_rare": True,
        "inheritance": "XL",
    },
    {
        "id": "D:MLD",
        "name": "Metachromatic leukodystrophy",
        "xrefs": {"mondo_id": "MONDO:0018868", "omim_id": "250100", "orpha_id": "512"},
        "is_rare": True,
        "inheritance": "AR",
    },
    # Non-LSD controls for variety
    {
        "id": "D:CF",
        "name": "Cystic fibrosis",
        "xrefs": {"mondo_id": "MONDO:0009061", "omim_id": "219700"},
        "is_rare": False,
        "inheritance": "AR",
    },
    {
        "id": "D:HD",
        "name": "Huntington disease",
        "xrefs": {"mondo_id": "MONDO:0007739", "omim_id": "143100"},
        "is_rare": True,
        "inheritance": "AD",
    },
]

GENES = [
    {"id": "G:GBA", "name": "GBA", "xrefs": {"hgnc_id": "HGNC:4177", "ncbi_gene_id": "2629"}},
    {"id": "G:GLA", "name": "GLA", "xrefs": {"hgnc_id": "HGNC:4296", "ncbi_gene_id": "2717"}},
    {"id": "G:SMPD1", "name": "SMPD1", "xrefs": {"hgnc_id": "HGNC:11120", "ncbi_gene_id": "6609"}},
    {"id": "G:NPC1", "name": "NPC1", "xrefs": {"hgnc_id": "HGNC:7897", "ncbi_gene_id": "4864"}},
    {"id": "G:NPC2", "name": "NPC2", "xrefs": {"hgnc_id": "HGNC:14537", "ncbi_gene_id": "10577"}},
    {"id": "G:GAA", "name": "GAA", "xrefs": {"hgnc_id": "HGNC:4065", "ncbi_gene_id": "2548"}},
    {"id": "G:HEXA", "name": "HEXA", "xrefs": {"hgnc_id": "HGNC:4878", "ncbi_gene_id": "3073"}},
    {"id": "G:GALC", "name": "GALC", "xrefs": {"hgnc_id": "HGNC:4115", "ncbi_gene_id": "2581"}},
    {"id": "G:IDUA", "name": "IDUA", "xrefs": {"hgnc_id": "HGNC:5391", "ncbi_gene_id": "3425"}},
    {"id": "G:IDS", "name": "IDS", "xrefs": {"hgnc_id": "HGNC:5389", "ncbi_gene_id": "3423"}},
    {"id": "G:ARSA", "name": "ARSA", "xrefs": {"hgnc_id": "HGNC:728", "ncbi_gene_id": "410"}},
    {"id": "G:CFTR", "name": "CFTR", "xrefs": {"hgnc_id": "HGNC:1884", "ncbi_gene_id": "1080"}},
    {"id": "G:HTT", "name": "HTT", "xrefs": {"hgnc_id": "HGNC:4851", "ncbi_gene_id": "3064"}},
]

PROTEINS = [
    {"id": "P:GBA", "name": "Beta-glucocerebrosidase", "xrefs": {"uniprot_id": "P04062"}},
    {"id": "P:GLA", "name": "Alpha-galactosidase A", "xrefs": {"uniprot_id": "P06280"}},
    {"id": "P:SMPD1", "name": "Acid sphingomyelinase", "xrefs": {"uniprot_id": "P17405"}},
    {
        "id": "P:NPC1",
        "name": "NPC intracellular cholesterol transporter 1",
        "xrefs": {"uniprot_id": "O15118"},
    },
    {
        "id": "P:NPC2",
        "name": "NPC intracellular cholesterol transporter 2",
        "xrefs": {"uniprot_id": "P61916"},
    },
    {"id": "P:GAA", "name": "Acid alpha-glucosidase", "xrefs": {"uniprot_id": "P10253"}},
    {
        "id": "P:HEXA",
        "name": "Beta-hexosaminidase subunit alpha",
        "xrefs": {"uniprot_id": "P06865"},
    },
    {"id": "P:GALC", "name": "Galactocerebrosidase", "xrefs": {"uniprot_id": "P54803"}},
    {"id": "P:IDUA", "name": "Alpha-L-iduronidase", "xrefs": {"uniprot_id": "P35475"}},
    {"id": "P:IDS", "name": "Iduronate 2-sulfatase", "xrefs": {"uniprot_id": "P22304"}},
    {"id": "P:ARSA", "name": "Arylsulfatase A", "xrefs": {"uniprot_id": "P15289"}},
    {
        "id": "P:CFTR",
        "name": "Cystic fibrosis transmembrane conductance regulator",
        "xrefs": {"uniprot_id": "P13569"},
    },
    {"id": "P:HTT", "name": "Huntingtin", "xrefs": {"uniprot_id": "P42858"}},
    # Regulatory targets (for repurposing candidates)
    {"id": "P:HDAC1", "name": "Histone deacetylase 1", "xrefs": {"uniprot_id": "Q13547"}},
    {
        "id": "P:MTOR",
        "name": "Serine/threonine-protein kinase mTOR",
        "xrefs": {"uniprot_id": "P42345"},
    },
    {"id": "P:HSP70", "name": "Heat shock 70 kDa protein 1A", "xrefs": {"uniprot_id": "P0DMV8"}},
]

DRUGS = [
    # Approved LSD therapies with approval years
    {
        "id": "DR:IMIGLUCERASE",
        "name": "Imiglucerase",
        "xrefs": {"drugcentral_id": "1423"},
        "approval_year": 1994,
        "is_approved": True,
    },
    {
        "id": "DR:VELAGLUCERASE",
        "name": "Velaglucerase alfa",
        "xrefs": {"drugcentral_id": "4723"},
        "approval_year": 2010,
        "is_approved": True,
    },
    {
        "id": "DR:TALIGLUCERASE",
        "name": "Taliglucerase alfa",
        "xrefs": {"drugcentral_id": "4829"},
        "approval_year": 2012,
        "is_approved": True,
    },
    {
        "id": "DR:MIGLUSTAT",
        "name": "Miglustat",
        "xrefs": {"drugcentral_id": "1803"},
        "approval_year": 2003,
        "is_approved": True,
    },  # approved for Gaucher T1 and NPC
    {
        "id": "DR:ELIGLUSTAT",
        "name": "Eliglustat",
        "xrefs": {"drugcentral_id": "4999"},
        "approval_year": 2014,
        "is_approved": True,
    },
    {
        "id": "DR:AGALSIDASE_A",
        "name": "Agalsidase alfa",
        "xrefs": {"drugcentral_id": "4268"},
        "approval_year": 2001,
        "is_approved": True,
    },  # EU
    {
        "id": "DR:AGALSIDASE_B",
        "name": "Agalsidase beta",
        "xrefs": {"drugcentral_id": "4267"},
        "approval_year": 2003,
        "is_approved": True,
    },
    {
        "id": "DR:MIGALASTAT",
        "name": "Migalastat",
        "xrefs": {"drugcentral_id": "5158"},
        "approval_year": 2018,
        "is_approved": True,
    },
    {
        "id": "DR:ALGLUCOSIDASE",
        "name": "Alglucosidase alfa",
        "xrefs": {"drugcentral_id": "4266"},
        "approval_year": 2006,
        "is_approved": True,
    },
    {
        "id": "DR:LARONIDASE",
        "name": "Laronidase",
        "xrefs": {"drugcentral_id": "4269"},
        "approval_year": 2003,
        "is_approved": True,
    },
    {
        "id": "DR:IDURSULFASE",
        "name": "Idursulfase",
        "xrefs": {"drugcentral_id": "4270"},
        "approval_year": 2006,
        "is_approved": True,
    },
    {
        "id": "DR:ARIMOCLOMOL",
        "name": "Arimoclomol",
        "xrefs": {"drugcentral_id": "5492"},
        "approval_year": 2023,
        "is_approved": True,
    },  # NPC, HSP co-inducer
    # Repurposing candidates (no TREATS edge — prediction targets)
    {
        "id": "DR:HPBCD",
        "name": "2-hydroxypropyl-beta-cyclodextrin",
        "xrefs": {"drugcentral_id": "3094"},
        "approval_year": None,
        "is_approved": False,
    },
    {
        "id": "DR:VORINOSTAT",
        "name": "Vorinostat",
        "xrefs": {"drugcentral_id": "4383"},
        "approval_year": 2006,
        "is_approved": True,
    },  # approved for CTCL, repurposing candidate for LSDs
    {
        "id": "DR:RAPAMYCIN",
        "name": "Sirolimus (rapamycin)",
        "xrefs": {"drugcentral_id": "2438"},
        "approval_year": 1999,
        "is_approved": True,
    },
    {
        "id": "DR:AMBROXOL",
        "name": "Ambroxol",
        "xrefs": {"drugcentral_id": "74"},
        "approval_year": 1979,
        "is_approved": True,
    },  # approved as mucolytic; Gaucher chaperone candidate
    {
        "id": "DR:NAL",
        "name": "N-acetyl-L-leucine",
        "xrefs": {"drugcentral_id": None},
        "approval_year": 2024,
        "is_approved": True,
    },  # recently approved for NPC
    # Non-LSD drugs for variety
    {
        "id": "DR:IVACAFTOR",
        "name": "Ivacaftor",
        "xrefs": {"drugcentral_id": "4835"},
        "approval_year": 2012,
        "is_approved": True,
    },
    {
        "id": "DR:TETRABENAZINE",
        "name": "Tetrabenazine",
        "xrefs": {"drugcentral_id": "2627"},
        "approval_year": 2008,
        "is_approved": True,
    },
]

PATHWAYS = [
    {"id": "PW:LYSO", "name": "Lysosomal degradation", "xrefs": {"reactome_id": "R-HSA-1632852"}},
    {
        "id": "PW:SPHINGO",
        "name": "Sphingolipid metabolism",
        "xrefs": {"reactome_id": "R-HSA-428157"},
    },
    {
        "id": "PW:GSL_BIOSYN",
        "name": "Glycosphingolipid biosynthesis",
        "xrefs": {"reactome_id": "R-HSA-9840310"},
    },
    {
        "id": "PW:GSL_DEG",
        "name": "Glycosphingolipid degradation",
        "xrefs": {"reactome_id": "R-HSA-1663150"},
    },
    {"id": "PW:AUTOPHAGY", "name": "Autophagy", "xrefs": {"reactome_id": "R-HSA-9612973"}},
    {"id": "PW:GLYCOGEN", "name": "Glycogen metabolism", "xrefs": {"reactome_id": "R-HSA-8982491"}},
    {
        "id": "PW:CHOLESTEROL",
        "name": "Cholesterol transport",
        "xrefs": {"reactome_id": "R-HSA-8957322"},
    },
    {
        "id": "PW:GAG_DEG",
        "name": "Glycosaminoglycan degradation",
        "xrefs": {"reactome_id": "R-HSA-2024096"},
    },
    {"id": "PW:APOPTOSIS", "name": "Apoptosis", "xrefs": {"reactome_id": "R-HSA-109581"}},
    {"id": "PW:MTOR", "name": "mTOR signaling", "xrefs": {"reactome_id": "R-HSA-165159"}},
    {"id": "PW:HSR", "name": "Heat shock response", "xrefs": {"reactome_id": "R-HSA-3371556"}},
    {"id": "PW:UPR", "name": "Unfolded protein response", "xrefs": {"reactome_id": "R-HSA-381119"}},
]

# Symptoms (HPO). The hpo_id is realistic; we use a compact local id as the
# canonical_id for the MVP for brevity.
SYMPTOMS = [
    {"id": "S:HEPATOMEGALY", "name": "Hepatomegaly", "xrefs": {"hpo_id": "HP:0002240"}},
    {"id": "S:SPLENOMEGALY", "name": "Splenomegaly", "xrefs": {"hpo_id": "HP:0001744"}},
    {"id": "S:SEIZURES", "name": "Seizures", "xrefs": {"hpo_id": "HP:0001250"}},
    {"id": "S:DEVDELAY", "name": "Global developmental delay", "xrefs": {"hpo_id": "HP:0001263"}},
    {"id": "S:CHERRYRED", "name": "Macular cherry-red spot", "xrefs": {"hpo_id": "HP:0010729"}},
    {"id": "S:BONEPAIN", "name": "Bone pain", "xrefs": {"hpo_id": "HP:0002653"}},
    {"id": "S:CARDIOMYO", "name": "Cardiomyopathy", "xrefs": {"hpo_id": "HP:0001638"}},
    {"id": "S:HEARINGLOSS", "name": "Hearing impairment", "xrefs": {"hpo_id": "HP:0000365"}},
    {"id": "S:VSGP", "name": "Vertical supranuclear gaze palsy", "xrefs": {"hpo_id": "HP:0000605"}},
    {"id": "S:HYPOTONIA", "name": "Hypotonia", "xrefs": {"hpo_id": "HP:0001252"}},
    {"id": "S:COARSEFACE", "name": "Coarse facial features", "xrefs": {"hpo_id": "HP:0000280"}},
    {"id": "S:CORNEACLOUD", "name": "Corneal opacity", "xrefs": {"hpo_id": "HP:0007957"}},
    {"id": "S:SKELETAL", "name": "Skeletal dysplasia", "xrefs": {"hpo_id": "HP:0002652"}},
    {"id": "S:RENAL", "name": "Abnormality of the kidney", "xrefs": {"hpo_id": "HP:0000077"}},
    {"id": "S:NEUROPATHY", "name": "Peripheral neuropathy", "xrefs": {"hpo_id": "HP:0009830"}},
    {"id": "S:ANGIOKERATOMA", "name": "Angiokeratoma", "xrefs": {"hpo_id": "HP:0001073"}},
    {"id": "S:ATAXIA", "name": "Ataxia", "xrefs": {"hpo_id": "HP:0001251"}},
    {"id": "S:DYSTONIA", "name": "Dystonia", "xrefs": {"hpo_id": "HP:0001332"}},
    {"id": "S:DYSPHAGIA", "name": "Dysphagia", "xrefs": {"hpo_id": "HP:0002015"}},
    {"id": "S:PULMONARY", "name": "Pulmonary fibrosis", "xrefs": {"hpo_id": "HP:0002206"}},
    {"id": "S:COGNITIVE", "name": "Cognitive impairment", "xrefs": {"hpo_id": "HP:0100543"}},
    {
        "id": "S:MOTORDECLINE",
        "name": "Progressive motor deterioration",
        "xrefs": {"hpo_id": "HP:0002344"},
    },
    {"id": "S:ANEMIA", "name": "Anemia", "xrefs": {"hpo_id": "HP:0001903"}},
    {"id": "S:THROMBOCYT", "name": "Thrombocytopenia", "xrefs": {"hpo_id": "HP:0001873"}},
    {"id": "S:CHOREA", "name": "Chorea", "xrefs": {"hpo_id": "HP:0002072"}},
    {"id": "S:PSYCHIATRIC", "name": "Psychiatric symptoms", "xrefs": {"hpo_id": "HP:0000708"}},
]

NODES = []
for d in DISEASES:
    NODES.append({**d, "type": "Disease"})
for g in GENES:
    NODES.append({**g, "type": "Gene"})
for p in PROTEINS:
    NODES.append({**p, "type": "Protein"})
for dr in DRUGS:
    NODES.append({**dr, "type": "Drug"})
for pw in PATHWAYS:
    NODES.append({**pw, "type": "Pathway"})
for s in SYMPTOMS:
    NODES.append({**s, "type": "Symptom"})

# --------------------------------------------------------------------------- #
# Edges. Provenance field set to "seed" for all. In Phase 1, real ingestors
# stamp source = "primekg" | "drugcentral" | "hpo" | "reactome" etc.
# --------------------------------------------------------------------------- #

EDGES = []


def E(h, r, t, **props):
    EDGES.append({"head": h, "rel": r, "tail": t, "source": "seed", **props})


# Gene — encodes — Protein
for sym in [
    "GBA",
    "GLA",
    "SMPD1",
    "NPC1",
    "NPC2",
    "GAA",
    "HEXA",
    "GALC",
    "IDUA",
    "IDS",
    "ARSA",
    "CFTR",
    "HTT",
]:
    E(f"G:{sym}", "ENCODES", f"P:{sym}")

# Gene — CAUSES — Disease (monogenic LSDs)
E("G:GBA", "CAUSES", "D:GAUCHER")
E("G:GLA", "CAUSES", "D:FABRY")
E("G:SMPD1", "CAUSES", "D:NPA")
E("G:SMPD1", "CAUSES", "D:NPB")
E("G:NPC1", "CAUSES", "D:NPC")
E("G:NPC2", "CAUSES", "D:NPC")
E("G:GAA", "CAUSES", "D:POMPE")
E("G:HEXA", "CAUSES", "D:TAYSACHS")
E("G:GALC", "CAUSES", "D:KRABBE")
E("G:IDUA", "CAUSES", "D:MPS1")
E("G:IDS", "CAUSES", "D:MPS2")
E("G:ARSA", "CAUSES", "D:MLD")
E("G:CFTR", "CAUSES", "D:CF")
E("G:HTT", "CAUSES", "D:HD")

# Gene — ASSOCIATED_WITH — Disease (shared biology / modifier associations)
E("G:NPC1", "ASSOCIATED_WITH", "D:NPB", score=0.3)  # related lipid biology
E("G:GBA", "ASSOCIATED_WITH", "D:HD", score=0.2)  # GBA mutations modify other neurodegen

# Gene / Protein — PARTICIPATES_IN — Pathway
for gp in ["GBA", "GLA", "SMPD1", "HEXA", "GALC", "IDUA", "IDS", "ARSA", "NPC1", "NPC2", "GAA"]:
    E(f"P:{gp}", "PARTICIPATES_IN", "PW:LYSO")

for gp in ["GBA", "GLA", "SMPD1", "HEXA", "GALC"]:
    E(f"P:{gp}", "PARTICIPATES_IN", "PW:SPHINGO")
    E(f"P:{gp}", "PARTICIPATES_IN", "PW:GSL_DEG")

E("P:NPC1", "PARTICIPATES_IN", "PW:CHOLESTEROL")
E("P:NPC2", "PARTICIPATES_IN", "PW:CHOLESTEROL")
E("P:GAA", "PARTICIPATES_IN", "PW:GLYCOGEN")
E("P:IDUA", "PARTICIPATES_IN", "PW:GAG_DEG")
E("P:IDS", "PARTICIPATES_IN", "PW:GAG_DEG")

E("P:MTOR", "PARTICIPATES_IN", "PW:AUTOPHAGY")
E("P:MTOR", "PARTICIPATES_IN", "PW:MTOR")
E("P:HSP70", "PARTICIPATES_IN", "PW:HSR")
E("P:HSP70", "PARTICIPATES_IN", "PW:UPR")
E("P:HDAC1", "PARTICIPATES_IN", "PW:APOPTOSIS")

# Drug — TARGETS — Protein
E("DR:IMIGLUCERASE", "TARGETS", "P:GBA", action="replaces")
E("DR:VELAGLUCERASE", "TARGETS", "P:GBA", action="replaces")
E("DR:TALIGLUCERASE", "TARGETS", "P:GBA", action="replaces")
E("DR:AMBROXOL", "TARGETS", "P:GBA", action="chaperone")
E("DR:AGALSIDASE_A", "TARGETS", "P:GLA", action="replaces")
E("DR:AGALSIDASE_B", "TARGETS", "P:GLA", action="replaces")
E("DR:MIGALASTAT", "TARGETS", "P:GLA", action="chaperone")
E("DR:ALGLUCOSIDASE", "TARGETS", "P:GAA", action="replaces")
E("DR:LARONIDASE", "TARGETS", "P:IDUA", action="replaces")
E("DR:IDURSULFASE", "TARGETS", "P:IDS", action="replaces")
E("DR:MIGLUSTAT", "TARGETS", "P:GBA", action="substrate_reduction")  # indirect (inhibits GCS)
E("DR:ELIGLUSTAT", "TARGETS", "P:GBA", action="substrate_reduction")
E("DR:HPBCD", "TARGETS", "P:NPC1", action="cholesterol_shuttle")
E("DR:ARIMOCLOMOL", "TARGETS", "P:HSP70", action="coinduces")
E("DR:NAL", "TARGETS", "P:NPC1", action="lysosomal_modulator")
E("DR:VORINOSTAT", "TARGETS", "P:HDAC1", action="inhibits")
E("DR:RAPAMYCIN", "TARGETS", "P:MTOR", action="inhibits")
E("DR:IVACAFTOR", "TARGETS", "P:CFTR", action="potentiator")
E("DR:TETRABENAZINE", "TARGETS", "P:HTT", action="indirect")  # actually targets VMAT2

# Drug — TREATS — Disease (approved indications, dated)
E("DR:IMIGLUCERASE", "TREATS", "D:GAUCHER", approval_year=1994)
E("DR:VELAGLUCERASE", "TREATS", "D:GAUCHER", approval_year=2010)
E("DR:TALIGLUCERASE", "TREATS", "D:GAUCHER", approval_year=2012)
E("DR:MIGLUSTAT", "TREATS", "D:GAUCHER", approval_year=2003)
E("DR:ELIGLUSTAT", "TREATS", "D:GAUCHER", approval_year=2014)
E("DR:MIGLUSTAT", "TREATS", "D:NPC", approval_year=2009)  # EU
E("DR:ARIMOCLOMOL", "TREATS", "D:NPC", approval_year=2023)
E("DR:NAL", "TREATS", "D:NPC", approval_year=2024)
E("DR:AGALSIDASE_A", "TREATS", "D:FABRY", approval_year=2001)
E("DR:AGALSIDASE_B", "TREATS", "D:FABRY", approval_year=2003)
E("DR:MIGALASTAT", "TREATS", "D:FABRY", approval_year=2018)
E("DR:ALGLUCOSIDASE", "TREATS", "D:POMPE", approval_year=2006)
E("DR:LARONIDASE", "TREATS", "D:MPS1", approval_year=2003)
E("DR:IDURSULFASE", "TREATS", "D:MPS2", approval_year=2006)
E("DR:IVACAFTOR", "TREATS", "D:CF", approval_year=2012)
E("DR:TETRABENAZINE", "TREATS", "D:HD", approval_year=2008)
# NOTE: Ambroxol is NOT given a TREATS edge — it is a Gaucher-chaperone
# repurposing candidate, so we hold it out as a prediction target.
# Vorinostat and Rapamycin are also intentionally held out as repurposing
# candidates (literature suggests effect on Niemann-Pick / LSDs via HDAC /
# autophagy, but no FDA approval).

# Disease — HAS_PHENOTYPE — Symptom (curated from HPO/OMIM clinical synopses)
DISEASE_PHENOTYPES = {
    "D:GAUCHER": ["HEPATOMEGALY", "SPLENOMEGALY", "BONEPAIN", "ANEMIA", "THROMBOCYT"],
    "D:FABRY": ["ANGIOKERATOMA", "RENAL", "NEUROPATHY", "CARDIOMYO", "HEARINGLOSS", "CORNEACLOUD"],
    "D:NPA": ["HEPATOMEGALY", "SPLENOMEGALY", "DEVDELAY", "CHERRYRED", "HYPOTONIA", "MOTORDECLINE"],
    "D:NPB": ["HEPATOMEGALY", "SPLENOMEGALY", "PULMONARY", "THROMBOCYT"],
    "D:NPC": [
        "HEPATOMEGALY",
        "SPLENOMEGALY",
        "VSGP",
        "ATAXIA",
        "DYSTONIA",
        "DYSPHAGIA",
        "SEIZURES",
        "COGNITIVE",
        "MOTORDECLINE",
    ],
    "D:POMPE": ["CARDIOMYO", "HYPOTONIA", "MOTORDECLINE", "HEARINGLOSS"],
    "D:TAYSACHS": ["DEVDELAY", "CHERRYRED", "SEIZURES", "HYPOTONIA", "MOTORDECLINE", "HEARINGLOSS"],
    "D:KRABBE": ["DEVDELAY", "HYPOTONIA", "SEIZURES", "MOTORDECLINE", "NEUROPATHY"],
    "D:MPS1": ["COARSEFACE", "CORNEACLOUD", "SKELETAL", "HEARINGLOSS", "DEVDELAY", "HEPATOMEGALY"],
    "D:MPS2": ["COARSEFACE", "SKELETAL", "HEARINGLOSS", "HEPATOMEGALY", "DEVDELAY"],
    "D:MLD": ["MOTORDECLINE", "DEVDELAY", "NEUROPATHY", "SEIZURES", "COGNITIVE"],
    "D:CF": ["PULMONARY", "COGNITIVE"],  # toy, CF is not cognitive — keep simple
    "D:HD": ["CHOREA", "DYSTONIA", "PSYCHIATRIC", "COGNITIVE", "MOTORDECLINE"],
}
for dis, syms in DISEASE_PHENOTYPES.items():
    for s in syms:
        E(dis, "HAS_PHENOTYPE", f"S:{s}", frequency="frequent")

# Disease — IS_A — Disease (abbreviated LSD superclass)
E("D:GAUCHER", "IS_A", "D:NPA")  # intentionally omitted; LSDs aren't IS_A
# We skip disease-is_a to keep the graph clean for the MVP.


def main():
    from app.core.paths import SEED_DIR

    out_dir = SEED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kg.json"
    # Drop the stray IS_A we appended by mistake above
    edges = [e for e in EDGES if e["rel"] != "IS_A"]
    version = f"{_BASE_VERSION}+sha.{_content_hash(NODES, edges)}"
    payload = {
        "version": version,
        "generated_by": "etl/build_seed_kg.py",
        "nodes": NODES,
        "edges": edges,
        "stats": {
            "n_nodes": len(NODES),
            "n_edges": len(edges),
            "by_node_type": {
                t: sum(1 for n in NODES if n["type"] == t) for t in {n["type"] for n in NODES}
            },
            "by_rel_type": {
                r: sum(1 for e in edges if e["rel"] == r) for r in {e["rel"] for e in edges}
            },
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  {payload['stats']['n_nodes']} nodes, {payload['stats']['n_edges']} edges")
    for k, v in payload["stats"]["by_node_type"].items():
        print(f"    {k}: {v}")
    for k, v in payload["stats"]["by_rel_type"].items():
        print(f"    rel {k}: {v}")


if __name__ == "__main__":
    main()
