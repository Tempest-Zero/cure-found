/**
 * Real CureFound KG fallbacks — mirrors `data/seed/kg.json` exactly so
 * the UI is demo-able even if the backend is offline. Live API responses
 * replace these on success.
 *
 * The API contract (request + response shapes) matches `app/repurpose/
 * schemas.py` and `app/diagnose/schemas.py` verbatim.
 */

export type EntityType = "Disease" | "Drug" | "Gene" | "Protein" | "Pathway" | "Symptom";

/* ---------------------------------------------------------------------------
 * Repurpose API contract — matches app/repurpose/schemas.py
 * ------------------------------------------------------------------------- */

export interface EvidenceEdge {
  from: string;
  to: string;
  rel: string;
  direction?: "forward" | "reverse" | null;
  approval_year?: number | null;
  action?: string | null;
  provenance?: string | null;
}

export interface RepurposeCandidate {
  drug_id: string;
  drug_name: string;
  model_score: number;
  graph_score: number;
  fused_score: number;
  model_rank: number;
  graph_rank: number;
  already_approved: boolean;
  approval_year: number | null;
  evidence_paths: EvidenceEdge[][];
}

export interface RepurposeResponse {
  disease_id: string;
  disease_name: string;
  candidates: RepurposeCandidate[];
}

/* ---------------------------------------------------------------------------
 * Diagnose API contract — matches app/diagnose/schemas.py
 * ------------------------------------------------------------------------- */

export interface SymptomBrief {
  id: string;
  name: string;
  hpo_id?: string | null;
}

export interface DiagnoseCandidate {
  disease_id: string;
  disease_name: string;
  jaccard_score: number;
  idf_score: number;
  fused_score: number;
  matched_symptoms: SymptomBrief[];
  missing_symptoms: SymptomBrief[];
  is_rare: boolean;
}

export interface DiagnoseResponse {
  resolved_inputs: string[];
  unresolved_inputs: string[];
  candidates: DiagnoseCandidate[];
}

/* ---------------------------------------------------------------------------
 * KG search / subgraph contracts — match app/kg/schemas.py
 * ------------------------------------------------------------------------- */

export interface NodeBrief {
  id: string;
  name: string;
  type: string;
  xrefs?: Record<string, unknown> | null;
}

export interface SubgraphNode { data: Record<string, unknown> }
export interface SubgraphEdge { data: Record<string, unknown> }
export interface SubgraphResponse {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

export interface StatsResponse {
  kg_version: string;
  n_entities: number;
  n_relations: number;
  n_triples: number;
  by_node_type: Record<string, number>;
  by_rel_type: Record<string, number>;
}

/* ---------------------------------------------------------------------------
 * Real entity vocab — extracted from data/seed/kg.json (99 nodes, 163 edges)
 * ------------------------------------------------------------------------- */

export interface NodeMeta {
  id: string;
  name: string;
  type: EntityType;
  is_rare?: boolean;
  approval_year?: number | null;
  is_approved?: boolean;
}

export const DISEASES: NodeMeta[] = [
  { id: "D:GAUCHER",  name: "Gaucher disease",                 type: "Disease", is_rare: true },
  { id: "D:FABRY",    name: "Fabry disease",                   type: "Disease", is_rare: true },
  { id: "D:NPC",      name: "Niemann-Pick disease type C",     type: "Disease", is_rare: true },
  { id: "D:NPA",      name: "Niemann-Pick disease type A",     type: "Disease", is_rare: true },
  { id: "D:NPB",      name: "Niemann-Pick disease type B",     type: "Disease", is_rare: true },
  { id: "D:POMPE",    name: "Pompe disease",                   type: "Disease", is_rare: true },
  { id: "D:TAYSACHS", name: "Tay-Sachs disease",               type: "Disease", is_rare: true },
  { id: "D:KRABBE",   name: "Krabbe disease",                  type: "Disease", is_rare: true },
  { id: "D:MPS1",     name: "Mucopolysaccharidosis type I",    type: "Disease", is_rare: true },
  { id: "D:MPS2",     name: "Mucopolysaccharidosis type II",   type: "Disease", is_rare: true },
  { id: "D:MLD",      name: "Metachromatic leukodystrophy",    type: "Disease", is_rare: true },
  { id: "D:CF",       name: "Cystic fibrosis",                 type: "Disease", is_rare: false },
  { id: "D:HD",       name: "Huntington disease",              type: "Disease", is_rare: true },
];

export const DRUGS: NodeMeta[] = [
  { id: "DR:IMIGLUCERASE", name: "Imiglucerase",                       type: "Drug", is_approved: true,  approval_year: 1994 },
  { id: "DR:VELAGLUCERASE",name: "Velaglucerase alfa",                 type: "Drug", is_approved: true,  approval_year: 2010 },
  { id: "DR:TALIGLUCERASE",name: "Taliglucerase alfa",                 type: "Drug", is_approved: true,  approval_year: 2012 },
  { id: "DR:MIGLUSTAT",    name: "Miglustat",                          type: "Drug", is_approved: true,  approval_year: 2003 },
  { id: "DR:ELIGLUSTAT",   name: "Eliglustat",                         type: "Drug", is_approved: true,  approval_year: 2014 },
  { id: "DR:AGALSIDASE_A", name: "Agalsidase alfa",                    type: "Drug", is_approved: true,  approval_year: 2001 },
  { id: "DR:AGALSIDASE_B", name: "Agalsidase beta",                    type: "Drug", is_approved: true,  approval_year: 2003 },
  { id: "DR:MIGALASTAT",   name: "Migalastat",                         type: "Drug", is_approved: true,  approval_year: 2018 },
  { id: "DR:ALGLUCOSIDASE",name: "Alglucosidase alfa",                 type: "Drug", is_approved: true,  approval_year: 2006 },
  { id: "DR:LARONIDASE",   name: "Laronidase",                         type: "Drug", is_approved: true,  approval_year: 2003 },
  { id: "DR:IDURSULFASE",  name: "Idursulfase",                        type: "Drug", is_approved: true,  approval_year: 2006 },
  { id: "DR:ARIMOCLOMOL",  name: "Arimoclomol",                        type: "Drug", is_approved: true,  approval_year: 2023 },
  { id: "DR:HPBCD",        name: "2-hydroxypropyl-beta-cyclodextrin",  type: "Drug", is_approved: false, approval_year: null },
  { id: "DR:VORINOSTAT",   name: "Vorinostat",                         type: "Drug", is_approved: true,  approval_year: 2006 },
  { id: "DR:RAPAMYCIN",    name: "Sirolimus (rapamycin)",              type: "Drug", is_approved: true,  approval_year: 1999 },
  { id: "DR:AMBROXOL",     name: "Ambroxol",                           type: "Drug", is_approved: true,  approval_year: 1979 },
  { id: "DR:NAL",          name: "N-acetyl-L-leucine",                 type: "Drug", is_approved: true,  approval_year: 2024 },
  { id: "DR:IVACAFTOR",    name: "Ivacaftor",                          type: "Drug", is_approved: true,  approval_year: 2012 },
  { id: "DR:TETRABENAZINE",name: "Tetrabenazine",                      type: "Drug", is_approved: true,  approval_year: 2008 },
];

export const SYMPTOMS: NodeMeta[] = [
  { id: "S:HEPATOMEGALY",  name: "Hepatomegaly",                     type: "Symptom" },
  { id: "S:SPLENOMEGALY",  name: "Splenomegaly",                     type: "Symptom" },
  { id: "S:SEIZURES",      name: "Seizures",                         type: "Symptom" },
  { id: "S:DEVDELAY",      name: "Global developmental delay",       type: "Symptom" },
  { id: "S:CHERRYRED",     name: "Macular cherry-red spot",          type: "Symptom" },
  { id: "S:BONEPAIN",      name: "Bone pain",                        type: "Symptom" },
  { id: "S:CARDIOMYO",     name: "Cardiomyopathy",                   type: "Symptom" },
  { id: "S:HEARINGLOSS",   name: "Hearing impairment",               type: "Symptom" },
  { id: "S:VSGP",          name: "Vertical supranuclear gaze palsy", type: "Symptom" },
  { id: "S:HYPOTONIA",     name: "Hypotonia",                        type: "Symptom" },
  { id: "S:COARSEFACE",    name: "Coarse facial features",           type: "Symptom" },
  { id: "S:CORNEACLOUD",   name: "Corneal opacity",                  type: "Symptom" },
  { id: "S:SKELETAL",      name: "Skeletal dysplasia",               type: "Symptom" },
  { id: "S:RENAL",         name: "Abnormality of the kidney",        type: "Symptom" },
  { id: "S:NEUROPATHY",    name: "Peripheral neuropathy",            type: "Symptom" },
  { id: "S:ANGIOKERATOMA", name: "Angiokeratoma",                    type: "Symptom" },
  { id: "S:ATAXIA",        name: "Ataxia",                           type: "Symptom" },
  { id: "S:DYSTONIA",      name: "Dystonia",                         type: "Symptom" },
  { id: "S:DYSPHAGIA",     name: "Dysphagia",                        type: "Symptom" },
  { id: "S:PULMONARY",     name: "Pulmonary fibrosis",               type: "Symptom" },
  { id: "S:COGNITIVE",     name: "Cognitive impairment",             type: "Symptom" },
  { id: "S:MOTORDECLINE",  name: "Progressive motor deterioration",  type: "Symptom" },
  { id: "S:ANEMIA",        name: "Anemia",                           type: "Symptom" },
  { id: "S:THROMBOCYT",    name: "Thrombocytopenia",                 type: "Symptom" },
  { id: "S:CHOREA",        name: "Chorea",                           type: "Symptom" },
  { id: "S:PSYCHIATRIC",   name: "Psychiatric symptoms",             type: "Symptom" },
];

export const GENES: NodeMeta[] = [
  { id: "G:GBA",   name: "GBA",   type: "Gene" },
  { id: "G:GLA",   name: "GLA",   type: "Gene" },
  { id: "G:SMPD1", name: "SMPD1", type: "Gene" },
  { id: "G:NPC1",  name: "NPC1",  type: "Gene" },
  { id: "G:NPC2",  name: "NPC2",  type: "Gene" },
  { id: "G:GAA",   name: "GAA",   type: "Gene" },
  { id: "G:HEXA",  name: "HEXA",  type: "Gene" },
  { id: "G:GALC",  name: "GALC",  type: "Gene" },
  { id: "G:IDUA",  name: "IDUA",  type: "Gene" },
  { id: "G:IDS",   name: "IDS",   type: "Gene" },
  { id: "G:ARSA",  name: "ARSA",  type: "Gene" },
  { id: "G:CFTR",  name: "CFTR",  type: "Gene" },
  { id: "G:HTT",   name: "HTT",   type: "Gene" },
];

export const PROTEINS: NodeMeta[] = [
  { id: "P:GBA",   name: "Beta-glucocerebrosidase",                          type: "Protein" },
  { id: "P:GLA",   name: "Alpha-galactosidase A",                            type: "Protein" },
  { id: "P:SMPD1", name: "Acid sphingomyelinase",                            type: "Protein" },
  { id: "P:NPC1",  name: "NPC intracellular cholesterol transporter 1",     type: "Protein" },
  { id: "P:NPC2",  name: "NPC intracellular cholesterol transporter 2",     type: "Protein" },
  { id: "P:GAA",   name: "Acid alpha-glucosidase",                           type: "Protein" },
  { id: "P:HEXA",  name: "Beta-hexosaminidase subunit alpha",                type: "Protein" },
  { id: "P:GALC", name: "Galactocerebrosidase",                              type: "Protein" },
  { id: "P:IDUA",  name: "Alpha-L-iduronidase",                              type: "Protein" },
  { id: "P:IDS",   name: "Iduronate 2-sulfatase",                            type: "Protein" },
  { id: "P:ARSA",  name: "Arylsulfatase A",                                  type: "Protein" },
  { id: "P:CFTR",  name: "CFTR transmembrane regulator",                     type: "Protein" },
  { id: "P:HTT",   name: "Huntingtin",                                       type: "Protein" },
  { id: "P:HDAC1", name: "Histone deacetylase 1",                            type: "Protein" },
  { id: "P:MTOR",  name: "mTOR kinase",                                      type: "Protein" },
  { id: "P:HSP70", name: "Heat shock 70kDa protein",                         type: "Protein" },
];

export const PATHWAYS: NodeMeta[] = [
  { id: "PW:LYSO",        name: "Lysosomal degradation",          type: "Pathway" },
  { id: "PW:SPHINGO",     name: "Sphingolipid metabolism",        type: "Pathway" },
  { id: "PW:GSL_BIOSYN",  name: "Glycosphingolipid biosynthesis", type: "Pathway" },
  { id: "PW:GSL_DEG",     name: "Glycosphingolipid degradation",  type: "Pathway" },
  { id: "PW:AUTOPHAGY",   name: "Autophagy",                      type: "Pathway" },
  { id: "PW:GLYCOGEN",    name: "Glycogen metabolism",            type: "Pathway" },
  { id: "PW:CHOLESTEROL", name: "Cholesterol transport",          type: "Pathway" },
  { id: "PW:GAG_DEG",     name: "Glycosaminoglycan degradation",  type: "Pathway" },
  { id: "PW:APOPTOSIS",   name: "Apoptosis",                      type: "Pathway" },
  { id: "PW:MTOR",        name: "mTOR signaling",                 type: "Pathway" },
  { id: "PW:HSR",         name: "Heat shock response",            type: "Pathway" },
  { id: "PW:UPR",         name: "Unfolded protein response",      type: "Pathway" },
];

/* All nodes flat — useful for id->meta lookups */
export const ALL_NODES: NodeMeta[] = [
  ...DISEASES, ...DRUGS, ...SYMPTOMS, ...GENES, ...PROTEINS, ...PATHWAYS,
];
export const NODE_BY_ID: Record<string, NodeMeta> = Object.fromEntries(
  ALL_NODES.map((n) => [n.id, n]),
);

/* ---------------------------------------------------------------------------
 * Real KG triples — extracted from data/seed/kg.json verbatim.
 * Used for the hero animated backdrop and the explorer.
 * ------------------------------------------------------------------------- */

export type Triple = [head: string, rel: string, tail: string];

export const EDGES: Triple[] = [
  // ENCODES (gene -> protein)
  ["G:GBA","ENCODES","P:GBA"], ["G:GLA","ENCODES","P:GLA"], ["G:SMPD1","ENCODES","P:SMPD1"],
  ["G:NPC1","ENCODES","P:NPC1"], ["G:NPC2","ENCODES","P:NPC2"], ["G:GAA","ENCODES","P:GAA"],
  ["G:HEXA","ENCODES","P:HEXA"], ["G:GALC","ENCODES","P:GALC"], ["G:IDUA","ENCODES","P:IDUA"],
  ["G:IDS","ENCODES","P:IDS"], ["G:ARSA","ENCODES","P:ARSA"], ["G:CFTR","ENCODES","P:CFTR"],
  ["G:HTT","ENCODES","P:HTT"],
  // CAUSES
  ["G:GBA","CAUSES","D:GAUCHER"], ["G:GLA","CAUSES","D:FABRY"],
  ["G:SMPD1","CAUSES","D:NPA"], ["G:SMPD1","CAUSES","D:NPB"],
  ["G:NPC1","CAUSES","D:NPC"], ["G:NPC2","CAUSES","D:NPC"],
  ["G:GAA","CAUSES","D:POMPE"], ["G:HEXA","CAUSES","D:TAYSACHS"],
  ["G:GALC","CAUSES","D:KRABBE"], ["G:IDUA","CAUSES","D:MPS1"],
  ["G:IDS","CAUSES","D:MPS2"], ["G:ARSA","CAUSES","D:MLD"],
  ["G:CFTR","CAUSES","D:CF"], ["G:HTT","CAUSES","D:HD"],
  // ASSOCIATED_WITH
  ["G:NPC1","ASSOCIATED_WITH","D:NPB"], ["G:GBA","ASSOCIATED_WITH","D:HD"],
  // PARTICIPATES_IN
  ["P:GBA","PARTICIPATES_IN","PW:LYSO"], ["P:GLA","PARTICIPATES_IN","PW:LYSO"],
  ["P:SMPD1","PARTICIPATES_IN","PW:LYSO"], ["P:HEXA","PARTICIPATES_IN","PW:LYSO"],
  ["P:GALC","PARTICIPATES_IN","PW:LYSO"], ["P:IDUA","PARTICIPATES_IN","PW:LYSO"],
  ["P:IDS","PARTICIPATES_IN","PW:LYSO"], ["P:ARSA","PARTICIPATES_IN","PW:LYSO"],
  ["P:NPC1","PARTICIPATES_IN","PW:LYSO"], ["P:NPC2","PARTICIPATES_IN","PW:LYSO"],
  ["P:GAA","PARTICIPATES_IN","PW:LYSO"],
  ["P:GBA","PARTICIPATES_IN","PW:SPHINGO"], ["P:GBA","PARTICIPATES_IN","PW:GSL_DEG"],
  ["P:GLA","PARTICIPATES_IN","PW:SPHINGO"], ["P:GLA","PARTICIPATES_IN","PW:GSL_DEG"],
  ["P:SMPD1","PARTICIPATES_IN","PW:SPHINGO"], ["P:SMPD1","PARTICIPATES_IN","PW:GSL_DEG"],
  ["P:HEXA","PARTICIPATES_IN","PW:SPHINGO"], ["P:HEXA","PARTICIPATES_IN","PW:GSL_DEG"],
  ["P:GALC","PARTICIPATES_IN","PW:SPHINGO"], ["P:GALC","PARTICIPATES_IN","PW:GSL_DEG"],
  ["P:NPC1","PARTICIPATES_IN","PW:CHOLESTEROL"], ["P:NPC2","PARTICIPATES_IN","PW:CHOLESTEROL"],
  ["P:GAA","PARTICIPATES_IN","PW:GLYCOGEN"],
  ["P:IDUA","PARTICIPATES_IN","PW:GAG_DEG"], ["P:IDS","PARTICIPATES_IN","PW:GAG_DEG"],
  ["P:MTOR","PARTICIPATES_IN","PW:AUTOPHAGY"], ["P:MTOR","PARTICIPATES_IN","PW:MTOR"],
  ["P:HSP70","PARTICIPATES_IN","PW:HSR"], ["P:HSP70","PARTICIPATES_IN","PW:UPR"],
  ["P:HDAC1","PARTICIPATES_IN","PW:APOPTOSIS"],
  // TARGETS
  ["DR:IMIGLUCERASE","TARGETS","P:GBA"], ["DR:VELAGLUCERASE","TARGETS","P:GBA"],
  ["DR:TALIGLUCERASE","TARGETS","P:GBA"], ["DR:AMBROXOL","TARGETS","P:GBA"],
  ["DR:AGALSIDASE_A","TARGETS","P:GLA"], ["DR:AGALSIDASE_B","TARGETS","P:GLA"],
  ["DR:MIGALASTAT","TARGETS","P:GLA"], ["DR:ALGLUCOSIDASE","TARGETS","P:GAA"],
  ["DR:LARONIDASE","TARGETS","P:IDUA"], ["DR:IDURSULFASE","TARGETS","P:IDS"],
  ["DR:MIGLUSTAT","TARGETS","P:GBA"], ["DR:ELIGLUSTAT","TARGETS","P:GBA"],
  ["DR:HPBCD","TARGETS","P:NPC1"], ["DR:ARIMOCLOMOL","TARGETS","P:HSP70"],
  ["DR:NAL","TARGETS","P:NPC1"], ["DR:VORINOSTAT","TARGETS","P:HDAC1"],
  ["DR:RAPAMYCIN","TARGETS","P:MTOR"], ["DR:IVACAFTOR","TARGETS","P:CFTR"],
  ["DR:TETRABENAZINE","TARGETS","P:HTT"],
  // TREATS
  ["DR:IMIGLUCERASE","TREATS","D:GAUCHER"], ["DR:VELAGLUCERASE","TREATS","D:GAUCHER"],
  ["DR:TALIGLUCERASE","TREATS","D:GAUCHER"], ["DR:MIGLUSTAT","TREATS","D:GAUCHER"],
  ["DR:ELIGLUSTAT","TREATS","D:GAUCHER"], ["DR:MIGLUSTAT","TREATS","D:NPC"],
  ["DR:ARIMOCLOMOL","TREATS","D:NPC"], ["DR:NAL","TREATS","D:NPC"],
  ["DR:AGALSIDASE_A","TREATS","D:FABRY"], ["DR:AGALSIDASE_B","TREATS","D:FABRY"],
  ["DR:MIGALASTAT","TREATS","D:FABRY"], ["DR:ALGLUCOSIDASE","TREATS","D:POMPE"],
  ["DR:LARONIDASE","TREATS","D:MPS1"], ["DR:IDURSULFASE","TREATS","D:MPS2"],
  ["DR:IVACAFTOR","TREATS","D:CF"], ["DR:TETRABENAZINE","TREATS","D:HD"],
  // HAS_PHENOTYPE
  ["D:GAUCHER","HAS_PHENOTYPE","S:HEPATOMEGALY"], ["D:GAUCHER","HAS_PHENOTYPE","S:SPLENOMEGALY"],
  ["D:GAUCHER","HAS_PHENOTYPE","S:BONEPAIN"], ["D:GAUCHER","HAS_PHENOTYPE","S:ANEMIA"],
  ["D:GAUCHER","HAS_PHENOTYPE","S:THROMBOCYT"],
  ["D:FABRY","HAS_PHENOTYPE","S:ANGIOKERATOMA"], ["D:FABRY","HAS_PHENOTYPE","S:RENAL"],
  ["D:FABRY","HAS_PHENOTYPE","S:NEUROPATHY"], ["D:FABRY","HAS_PHENOTYPE","S:CARDIOMYO"],
  ["D:FABRY","HAS_PHENOTYPE","S:HEARINGLOSS"], ["D:FABRY","HAS_PHENOTYPE","S:CORNEACLOUD"],
  ["D:NPA","HAS_PHENOTYPE","S:HEPATOMEGALY"], ["D:NPA","HAS_PHENOTYPE","S:SPLENOMEGALY"],
  ["D:NPA","HAS_PHENOTYPE","S:DEVDELAY"], ["D:NPA","HAS_PHENOTYPE","S:CHERRYRED"],
  ["D:NPA","HAS_PHENOTYPE","S:HYPOTONIA"], ["D:NPA","HAS_PHENOTYPE","S:MOTORDECLINE"],
  ["D:NPB","HAS_PHENOTYPE","S:HEPATOMEGALY"], ["D:NPB","HAS_PHENOTYPE","S:SPLENOMEGALY"],
  ["D:NPB","HAS_PHENOTYPE","S:PULMONARY"], ["D:NPB","HAS_PHENOTYPE","S:THROMBOCYT"],
  ["D:NPC","HAS_PHENOTYPE","S:HEPATOMEGALY"], ["D:NPC","HAS_PHENOTYPE","S:SPLENOMEGALY"],
  ["D:NPC","HAS_PHENOTYPE","S:VSGP"], ["D:NPC","HAS_PHENOTYPE","S:ATAXIA"],
  ["D:NPC","HAS_PHENOTYPE","S:DYSTONIA"], ["D:NPC","HAS_PHENOTYPE","S:DYSPHAGIA"],
  ["D:NPC","HAS_PHENOTYPE","S:SEIZURES"], ["D:NPC","HAS_PHENOTYPE","S:COGNITIVE"],
  ["D:NPC","HAS_PHENOTYPE","S:MOTORDECLINE"],
  ["D:POMPE","HAS_PHENOTYPE","S:CARDIOMYO"], ["D:POMPE","HAS_PHENOTYPE","S:HYPOTONIA"],
  ["D:POMPE","HAS_PHENOTYPE","S:MOTORDECLINE"], ["D:POMPE","HAS_PHENOTYPE","S:HEARINGLOSS"],
  ["D:TAYSACHS","HAS_PHENOTYPE","S:DEVDELAY"], ["D:TAYSACHS","HAS_PHENOTYPE","S:CHERRYRED"],
  ["D:TAYSACHS","HAS_PHENOTYPE","S:SEIZURES"], ["D:TAYSACHS","HAS_PHENOTYPE","S:HYPOTONIA"],
  ["D:TAYSACHS","HAS_PHENOTYPE","S:MOTORDECLINE"], ["D:TAYSACHS","HAS_PHENOTYPE","S:HEARINGLOSS"],
  ["D:KRABBE","HAS_PHENOTYPE","S:DEVDELAY"], ["D:KRABBE","HAS_PHENOTYPE","S:HYPOTONIA"],
  ["D:KRABBE","HAS_PHENOTYPE","S:SEIZURES"], ["D:KRABBE","HAS_PHENOTYPE","S:MOTORDECLINE"],
  ["D:KRABBE","HAS_PHENOTYPE","S:NEUROPATHY"],
  ["D:MPS1","HAS_PHENOTYPE","S:COARSEFACE"], ["D:MPS1","HAS_PHENOTYPE","S:CORNEACLOUD"],
  ["D:MPS1","HAS_PHENOTYPE","S:SKELETAL"], ["D:MPS1","HAS_PHENOTYPE","S:HEARINGLOSS"],
  ["D:MPS1","HAS_PHENOTYPE","S:DEVDELAY"], ["D:MPS1","HAS_PHENOTYPE","S:HEPATOMEGALY"],
  ["D:MPS2","HAS_PHENOTYPE","S:COARSEFACE"], ["D:MPS2","HAS_PHENOTYPE","S:SKELETAL"],
  ["D:MPS2","HAS_PHENOTYPE","S:HEARINGLOSS"], ["D:MPS2","HAS_PHENOTYPE","S:HEPATOMEGALY"],
  ["D:MPS2","HAS_PHENOTYPE","S:DEVDELAY"],
  ["D:MLD","HAS_PHENOTYPE","S:MOTORDECLINE"], ["D:MLD","HAS_PHENOTYPE","S:DEVDELAY"],
  ["D:MLD","HAS_PHENOTYPE","S:NEUROPATHY"], ["D:MLD","HAS_PHENOTYPE","S:SEIZURES"],
  ["D:MLD","HAS_PHENOTYPE","S:COGNITIVE"],
  ["D:CF","HAS_PHENOTYPE","S:PULMONARY"], ["D:CF","HAS_PHENOTYPE","S:COGNITIVE"],
  ["D:HD","HAS_PHENOTYPE","S:CHOREA"], ["D:HD","HAS_PHENOTYPE","S:DYSTONIA"],
  ["D:HD","HAS_PHENOTYPE","S:PSYCHIATRIC"], ["D:HD","HAS_PHENOTYPE","S:COGNITIVE"],
  ["D:HD","HAS_PHENOTYPE","S:MOTORDECLINE"],
];

/* ---------------------------------------------------------------------------
 * Demo presets — quick-pick chips for the diagnose section.
 * Uses real S:NAME ids; backend accepts S:* or HP:* interchangeably.
 * ------------------------------------------------------------------------- */

export interface DiagnosePreset {
  label: string;
  hint: string;
  symptoms: string[];
}

export const DIAGNOSE_PRESETS: DiagnosePreset[] = [
  {
    label: "Cherry-red + hypotonic infant",
    hint: "Tay-Sachs / NPA pattern",
    symptoms: ["S:CHERRYRED", "S:HYPOTONIA", "S:DEVDELAY", "S:SEIZURES"],
  },
  {
    label: "Vertical gaze palsy + ataxia",
    hint: "Niemann-Pick C pattern",
    symptoms: ["S:VSGP", "S:ATAXIA", "S:HEPATOMEGALY", "S:SPLENOMEGALY", "S:DYSTONIA"],
  },
  {
    label: "Angiokeratoma + renal + neuropathy",
    hint: "Fabry pattern",
    symptoms: ["S:ANGIOKERATOMA", "S:RENAL", "S:NEUROPATHY", "S:CARDIOMYO"],
  },
  {
    label: "Hepatosplenomegaly + bone pain",
    hint: "Gaucher pattern",
    symptoms: ["S:HEPATOMEGALY", "S:SPLENOMEGALY", "S:BONEPAIN", "S:ANEMIA", "S:THROMBOCYT"],
  },
  {
    label: "Chorea + psychiatric + cognitive",
    hint: "Huntington pattern",
    symptoms: ["S:CHOREA", "S:PSYCHIATRIC", "S:COGNITIVE", "S:DYSTONIA"],
  },
];

/* ---------------------------------------------------------------------------
 * Predicted-rank fallbacks intentionally omitted.
 *
 * Earlier versions of this file shipped hand-curated REPURPOSE_FALLBACK /
 * DIAGNOSE_FALLBACK objects so the UI could render plausible-looking ranks
 * even when the FastAPI backend was unreachable. After the HPO expansion +
 * RotatE retrain those static numbers became misleading — they no longer
 * matched the model the API actually serves. Showing them on screen while
 * the backend was down would be a quiet form of fake data.
 *
 * The sections now display an explicit empty/error state when the API
 * fails, gated by the LIVE / OFFLINE chip in ApiStatusChip.tsx. If you
 * need a deterministic demo dataset, run the backend locally — the dev
 * setup in README.md takes under a minute.
 * ------------------------------------------------------------------------- */

export const REPURPOSE_FALLBACK: Record<string, RepurposeResponse> = {};
export const DIAGNOSE_FALLBACK: Record<string, DiagnoseResponse> = {};

/* ---------------------------------------------------------------------------
 * Visual constants
 * ------------------------------------------------------------------------- */

export const ENTITY_COLORS: Record<EntityType, string> = {
  Disease: "var(--color-t-disease)",
  Drug:    "var(--color-t-drug)",
  Gene:    "var(--color-t-gene)",
  Protein: "var(--color-t-protein)",
  Pathway: "var(--color-t-pathway)",
  Symptom: "var(--color-t-symptom)",
};

export const NODE_TYPE: Record<string, EntityType> = Object.fromEntries(
  ALL_NODES.map((n) => [n.id, n.type]),
);
