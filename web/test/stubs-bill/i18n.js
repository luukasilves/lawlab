const STRINGS = {
  agreement: "Kooskõla",
  back: "Tagasi",
  checked: "kontrollitud",
  cluster_below: "alla läve (ei avaldata)",
  cluster_published: "avaldatud",
  clustering_step: "Klasterdamine",
  cost: "Kulu",
  description: "Kirjeldus",
  deterministic_count: "deterministlikku leidu",
  deterministic_step: "Deterministlikud kontrollid",
  dismiss: "Lükka tagasi",
  dropped: "välja jäetud",
  duration: "Kestus",
  evidence: "Katkend",
  feedback_error: "Tagasiside saatmine ebaõnnestus",
  feedback_thanks: "Aitäh tagasiside eest",
  finding_count: "leidu",
  found: "leiti",
  grounded: "tekstiga seotud",
  history: "Analüüside ajalugu",
  independent_analyses: "sõltumatut analüüsi",
  meta_committee: "Juhtivkomisjon",
  meta_prompt: "Prompt versioon",
  meta_type: "Liik",
  meta_updated: "Viimati uuendatud",
  methodology_data: "Metoodika andmed",
  no_data: "Andmed puuduvad",
  pipeline: "Analüüsi käik",
  raw_json: "Toorandmed JSON",
  raw_json_note: "Avalik võti pannakse päringu apikey päisesse.",
  reasoning: "Põhjendus",
  refuted: "ümber lükatud",
  refuted_section: "Ümber lükatud leiud",
  results: "Tulemused",
  returned: "tagastatud",
  sample_reused: "taaskasutatud",
  samples: "Valimid",
  sampling_step: "Tõlgenduslik valim",
  severity_HIGH: "Kõrge",
  severity_LOW: "Madal",
  severity_MEDIUM: "Keskmine",
  skeptic_refuted: "Ümber lükatud",
  skeptic_step: "Skeptiku kontroll",
  skeptic_upheld: "Kontrollitud",
  source_model: "Mudel",
  source_rule: "Reegel",
  suggestion: "Soovitus",
  summary_analyzed: "Analüüsitud",
  summary_chars: "märki",
  summary_documents: "Dokumendid",
  summary_prompt: "Prompt",
  threshold: "künnis",
  tokens: "Tokenid",
  totals_step: "Kokkuvõte",
  view_riigikogu: "Vaata Riigikogu veebis",
  zero_findings: "Avaldatavaid leide ei tuvastatud."
};

export function t(key) {
  return STRINGS[key] || key;
}

export function getLang() {
  return "et";
}

export function stripLang(pathname) {
  const path = pathname || "/";
  return path.replace(/^\/en(?=\/|$)/, "") || "/";
}

// Mirrors the real helper so bill.js can build language-aware links in tests.
export function withLang(canonicalPath, lang = "et") {
  let path = canonicalPath || "/";
  if (!path.startsWith("/")) {
    path = `/${path}`;
  }
  if (lang !== "en") {
    return path;
  }
  return path === "/" ? "/en" : `/en${path}`;
}
