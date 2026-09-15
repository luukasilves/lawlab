let getLangFromModule = null;
let lastMethodology = null;

const TEXT = {
  et: {
    pageTitle: "About",
    intro:
      "Apsakaleidja otsib seaduseelnõu tekstist normitehnilisi ja sisulise kooskõla riske. Leiud on masinanalüüs, mitte õiguslik hinnang: need aitavad tähelepanu suunata, kuid lõpliku otsuse teeb inimene eelnõu ja selle konteksti põhjal.",
    engine: "Mootor",
    provider: "Teenusepakkuja",
    model: "Mudel",
    sampling: "Valim",
    temperature: "Temperatuur",
    dataSources: "Andmeallikad",
    riigikoguApiTitle: "Riigikogu API",
    riigikoguApiBody: "Eelnõude nimekiri ja metaandmed loetakse Riigikogu avalikust API-st:",
    documentsTitle: "Dokumendid",
    documentsBody: "Analüüsitakse eelnõu põhiteksti DOCX- või DOC-failist. NB! Seletuskirja ei analüüsita.",
    refreshTitle: "Andmete uuendamine",
    refreshBody: "Andmed uuenevad automaatselt iga päev kell 05:00 UTC. Värskuse ajatempel pärineb pipeline_runs tabeli viimasest õnnestunud laadimisest. Iga lehe jalus näitab viimase kontrolli aega ja tulemust.",
    aiModel: "AI mudel",
    samplingLine: (s) => `Valim: ${s.samples ?? "?"} sõltumatut analüüsi, avaldamise künnis ${s.min_agreement ?? "?"}/${s.samples ?? "?"}, temperatuur ${s.temperature ?? "?"}.`,
    textLimitTitle: "Teksti piirang",
    textLimitBody: "Teksti ei kärbita: vana versioon piiras analüüsi 30 000 märgiga, uus versioon analüüsib kogu teksti.",
    systemPrompts: "Süsteemi promptid",
    showPrompt: (version) => `Näita ${version} prompti`,
    pipeline: "Analüüsi käik",
    checks: "Kontrollid",
    name: "Nimi",
    description: "Kirjeldus",
    category: "Kategooria",
    enabled: "Olek",
    version: "Versioon",
    on: "sees",
    off: "välja lülitatud",
    systemPrompt: "System prompt",
    userTemplate: "User template",
    promptSha: "Prompt SHA",
    categories: "Kategooriad ja HÕNTE",
    label: "Kategooria",
    honte: "HÕNTE viide",
    honteRules: "HÕNTE reeglite tekstid",
    limitations: "Piirangud",
    dataApi: "Andmed / API",
    tables: "Tabelid",
    examples: "Näited",
    repo: "GitHubi repositoorium",
    gold:
      "Kontrollkomplekt (gold set) on avalik eval_labels tabelis.",
    story: "Lugu",
    downloads: "Lae andmed alla",
    downloadsIntro:
      "Kogu analüüside andmebaasi saab alla laadida ühe klõpsuga. Failid koostatakse otse avalikust andmebaasist, seega on need alati sama värsked kui leht ise.",
    downloadsNote:
      "Eelnõude täistekstid failidesse ei mahu — need on kättesaadavad API kaudu (tabel bill_documents, veerg parsed_text).",
    downloading: (n) => `Laen... ${n} rida`,
    downloaded: (n) => `${n} rida`,
    downloadFailed: "Allalaadimine ebaõnnestus",
    datasets: {
      overview: ["Ülevaade", "Üks rida iga eelnõu kohta: staatus, viimane analüüs, leidude arv raskusastmete lõikes."],
      findings: ["Leiud", "Kõik leiud koos eelnõu numbri ja pealkirjaga — ka skeptiku poolt ümber lükatud."],
      analyses: ["Analüüsid", "Iga analüüsi mootorimanifest, statistika, kestus ja maksumus."],
      samples: ["Mudeli toorvastused", "Iga LLM-päringu töötlemata vastus (~15 MB)."],
      bills: ["Eelnõud", "Eelnõude metaandmed Riigikogu API-st."]
    },
    loadError: "Metoodika andmete laadimine ebaõnnestus.",
    pipelineText: {
      parse: ["Teksti lugemine", "Eelnõu põhitekst eraldatakse ja jagatakse analüüsitavateks osadeks."],
      deterministic: ["Deterministlikud kontrollid", "Reeglid otsivad mehaanilisi vigu, mida saab hinnata ilma keelemudelita."],
      interpretive: ["Tõlgenduslik analüüs", "Keelemudel otsib sisulisi riske ja peab iga leiu siduma tekstikohaga."],
      cluster: ["Kokku rühmitamine", "Sarnased kandidaadid koondatakse, et korduvad leiud oleksid võrreldavad."],
      dedup: ["Duplikaatide eemaldamine", "Sama probleemi kordused ühendatakse üheks leiuks."],
      refute: ["Skeptiku kontroll", "Eraldi kontrollsamm püüab nõrgad või halvasti põhjendatud leiud tagasi lükata."],
      persist: ["Salvestamine", "Püsivad leiud ja metaandmed salvestatakse avalikult loetavatesse tabelitesse."]
    }
  },
  en: {
    pageTitle: "About",
    intro:
      "Apsakaleidja searches the bill text for legislative-drafting and substantive consistency risks. Findings are machine analysis, not legal advice: they point attention to possible issues, while a person makes the final assessment from the bill and its context.",
    engine: "Engine",
    provider: "Provider",
    model: "Model",
    sampling: "Sampling",
    temperature: "Temperature",
    dataSources: "Data sources",
    riigikoguApiTitle: "Riigikogu API",
    riigikoguApiBody: "The bill list and metadata are read from the public Riigikogu API:",
    documentsTitle: "Documents",
    documentsBody: "The main bill text is analysed from the DOCX or DOC file. Note: the explanatory memorandum is not analysed.",
    refreshTitle: "Data refresh",
    refreshBody: "Data refreshes automatically every day at 05:00 UTC. The freshness timestamp comes from the last successful run in the pipeline_runs table. The footer of every page shows the time and outcome of the last check.",
    aiModel: "AI model",
    samplingLine: (s) => `Sampling: ${s.samples ?? "?"} independent analyses, publication threshold ${s.min_agreement ?? "?"}/${s.samples ?? "?"}, temperature ${s.temperature ?? "?"}.`,
    textLimitTitle: "Text limit",
    textLimitBody: "No truncation: the previous version capped analysis at 30,000 characters; the new version analyses the full text.",
    systemPrompts: "System prompts",
    showPrompt: (version) => `Show ${version} prompt`,
    pipeline: "Analysis flow",
    checks: "Checks",
    name: "Name",
    description: "Description",
    category: "Category",
    enabled: "Status",
    version: "Version",
    on: "enabled",
    off: "disabled",
    systemPrompt: "System prompt",
    userTemplate: "User template",
    promptSha: "Prompt SHA",
    categories: "Categories and HÕNTE",
    label: "Category",
    honte: "HÕNTE citation",
    honteRules: "HÕNTE rule texts",
    limitations: "Limitations",
    dataApi: "Data / API",
    tables: "Tables",
    examples: "Examples",
    repo: "GitHub repository",
    gold:
      "The gold-set review sample is public in the eval_labels table.",
    story: "The story",
    downloads: "Download the data",
    downloadsIntro:
      "The full analysis database is one click away. Files are built directly from the public database, so they are always as fresh as the page itself.",
    downloadsNote:
      "Full bill texts do not fit in these files — they are available through the API (bill_documents table, parsed_text column).",
    downloading: (n) => `Downloading... ${n} rows`,
    downloaded: (n) => `${n} rows`,
    downloadFailed: "Download failed",
    datasets: {
      overview: ["Overview", "One row per bill: status, latest analysis, finding counts by severity."],
      findings: ["Findings", "Every finding with the bill number and title — including those refuted by the skeptic pass."],
      analyses: ["Analyses", "Engine manifest, statistics, duration and cost of every analysis."],
      samples: ["Raw model outputs", "The unprocessed response of every LLM call (~15 MB)."],
      bills: ["Bills", "Bill metadata from the Riigikogu API."]
    },
    loadError: "Could not load methodology data.",
    pipelineText: {
      parse: ["Parse text", "The main bill text is extracted and split into analysable parts."],
      deterministic: ["Deterministic checks", "Rules look for mechanical errors that can be assessed without a language model."],
      interpretive: ["Interpretive analysis", "The language model looks for substantive risks and must ground every finding in the text."],
      cluster: ["Cluster", "Similar candidates are grouped so repeated findings can be compared."],
      dedup: ["Deduplicate", "Repeated reports of the same issue are merged into one finding."],
      refute: ["Skeptic review", "A separate review step tries to reject weak or poorly grounded findings."],
      persist: ["Persist", "Stable findings and metadata are stored in publicly readable tables."]
    }
  }
};

const moduleReady = Promise.allSettled([
  import("i18n").then((mod) => {
    if (typeof mod.getLang === "function") getLangFromModule = mod.getLang;
  }),
  import("shell").then((mod) => {
    if (typeof mod.initShell === "function") {
      mod.initShell();
    } else if (typeof mod.renderHeader === "function" && !window.__LAWLAB_TEST__) {
      // The real shell self-initializes on DOMContentLoaded, but this dynamic
      // import can resolve after that event has already fired — render directly.
      mod.renderHeader(document.body?.dataset.active || "method");
      if (typeof mod.renderFooter === "function") mod.renderFooter();
    }
  })
]);

function lang() {
  let value = null;
  try {
    value = getLangFromModule ? getLangFromModule() : null;
  } catch (_err) {
    value = null;
  }
  value = value || window.__metoodikaLang || document.documentElement.lang || "et";
  return String(value).toLowerCase().startsWith("en") ? "en" : "et";
}

function t() {
  return TEXT[lang()];
}

function field(item, base) {
  const suffix = lang() === "en" ? "_en" : "_et";
  return item?.[`${base}${suffix}`] || item?.[base] || "";
}

function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function section(id, title) {
  const node = el("section");
  if (id) node.id = id;
  node.appendChild(el("h2", null, title));
  return node;
}

function categoryMap(methodology) {
  const map = new Map();
  for (const category of methodology.categories || []) {
    map.set(category.key, field(category, "label"));
  }
  return map;
}

function renderStory(root, methodology) {
  const copy = t();
  const paragraphs = lang() === "en" ? methodology.story_en : methodology.story_et;
  if (!Array.isArray(paragraphs) || paragraphs.length === 0) return;
  const node = section("lugu", copy.story);
  const wrap = el("div", "story");
  for (const paragraph of paragraphs) {
    wrap.appendChild(el("p", null, paragraph));
  }
  node.appendChild(wrap);
  root.appendChild(node);
}

// ── Data downloads ───────────────────────────────────────────────────────────
// Files are assembled in the browser straight from the public REST API, so a
// download is always exactly as fresh as the page. Queries carry a stable
// order= because fetchAll pages with Range headers.

function flattenFinding(row) {
  const bill = row.analyses?.bill_documents?.bills || {};
  const { analyses, ...rest } = row;
  return { bill_number: bill.bill_number ?? null, bill_title: bill.title ?? null, ...rest };
}

const DATASETS = [
  {
    key: "overview",
    file: "apsakaleidja-ulevaade",
    formats: ["csv", "json"],
    query: "/rest/v1/bill_index?select=*&order=bill_number.asc",
    csvColumns: [
      "bill_number", "title", "status", "active_stage", "doc_fetched_at", "doc_version",
      "text_length", "extraction_method", "analyzed_at", "model", "prompt_version",
      "high_count", "medium_count", "low_count", "refuted_count",
      "bill_id", "document_id", "analysis_id"
    ]
  },
  {
    key: "findings",
    file: "apsakaleidja-leiud",
    formats: ["csv", "json"],
    query: "/rest/v1/findings?select=*,analyses(bill_document_id,bill_documents(bill_id,bills(bill_number,title)))&order=created_at.asc,id.asc",
    flatten: flattenFinding,
    csvColumns: [
      "bill_number", "bill_title", "severity", "category", "confidence",
      "runs_found", "runs_total", "skeptic_verdict", "source", "check_id",
      "location", "provision_id", "title", "description", "reasoning", "suggestion",
      "evidence_quote", "honte_rule", "skeptic_reasoning", "char_start", "char_end",
      "analysis_id", "id", "created_at"
    ]
  },
  {
    key: "analyses",
    file: "apsakaleidja-analyysid",
    formats: ["json"],
    query: "/rest/v1/analyses?select=*&order=created_at.asc,id.asc"
  },
  {
    key: "samples",
    file: "apsakaleidja-toorvastused",
    formats: ["json"],
    query: "/rest/v1/analysis_samples?select=*&order=created_at.asc,id.asc",
    pageSize: 200
  },
  {
    key: "bills",
    file: "apsakaleidja-eelnoud",
    formats: ["json"],
    query: "/rest/v1/bills?select=*&order=bill_number.asc"
  }
];

function csvValue(value) {
  if (value == null) return "";
  const s = typeof value === "object" ? JSON.stringify(value) : String(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(rows, columns) {
  const cols = columns || Object.keys(rows[0] || {});
  const lines = [cols.join(",")];
  for (const row of rows) {
    lines.push(cols.map((col) => csvValue(row[col])).join(","));
  }
  // BOM so spreadsheet apps detect UTF-8 (Estonian diacritics).
  return "\uFEFF" + lines.join("\r\n") + "\r\n";
}

function saveFile(filename, mime, content) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

async function runDownload(dataset, format, button, status) {
  const copy = t();
  if (button.disabled) return;
  const buttons = Array.from(button.parentElement.querySelectorAll("button"));
  buttons.forEach((b) => { b.disabled = true; });
  status.classList.remove("failed");
  status.textContent = copy.downloading(0);
  try {
    const { fetchAll } = await import("api");
    const rows = await fetchAll(dataset.query, {
      pageSize: dataset.pageSize || 1000,
      onProgress: (n) => { status.textContent = copy.downloading(n); }
    });
    const flat = dataset.flatten ? rows.map(dataset.flatten) : rows;
    const stamp = new Date().toISOString().slice(0, 10);
    if (format === "csv") {
      saveFile(`${dataset.file}-${stamp}.csv`, "text/csv;charset=utf-8", toCsv(flat, dataset.csvColumns));
    } else {
      saveFile(`${dataset.file}-${stamp}.json`, "application/json", JSON.stringify(flat));
    }
    status.textContent = copy.downloaded(flat.length);
  } catch (error) {
    console.error("download failed", dataset.key, error);
    status.textContent = copy.downloadFailed;
    status.classList.add("failed");
  } finally {
    buttons.forEach((b) => { b.disabled = false; });
  }
}

function renderDownloads(root) {
  const copy = t();
  const node = section("allalaadimine", copy.downloads);
  node.appendChild(el("p", "api-note", copy.downloadsIntro));
  const list = el("div", "downloads");
  for (const dataset of DATASETS) {
    const [name, desc] = copy.datasets[dataset.key] || [dataset.key, ""];
    const row = el("div", "download-row");
    row.dataset.dataset = dataset.key;
    const info = el("div", "download-info");
    info.appendChild(el("strong", null, name));
    info.appendChild(el("p", null, desc));
    row.appendChild(info);
    const actions = el("div", "download-actions");
    const status = el("span", "download-status", "");
    for (const format of dataset.formats) {
      const button = el("button", "download-btn", format.toUpperCase());
      button.type = "button";
      button.addEventListener("click", () => runDownload(dataset, format, button, status));
      actions.appendChild(button);
    }
    actions.appendChild(status);
    row.appendChild(actions);
    list.appendChild(row);
  }
  node.appendChild(list);
  node.appendChild(el("p", "gold-note", copy.downloadsNote));
  root.appendChild(node);
}

function renderHero(root, methodology) {
  const copy = t();
  const hero = el("div", "hero");
  hero.appendChild(el("h1", null, copy.pageTitle));
  hero.appendChild(el("p", "intro", copy.intro));

  const engine = methodology.engine || {};
  const sampling = engine.sampling || {};
  const metrics = el("div", "engine");
  [
    [copy.provider, engine.provider || ""],
    [copy.model, engine.model || ""],
    [copy.sampling, `${sampling.samples ?? "?"} / ${sampling.min_agreement ?? "?"}`],
    [copy.temperature, String(sampling.temperature ?? "")]
  ].forEach(([label, value]) => {
    const metric = el("div", "metric");
    metric.appendChild(el("b", null, label));
    metric.appendChild(el("span", null, value));
    metrics.appendChild(metric);
  });
  hero.appendChild(metrics);
  root.appendChild(hero);
}

// Old-site lead sections: Andmeallikad (Riigikogu API / Dokumendid /
// Andmete uuendamine) and AI mudel (model id, sampling, Teksti piirang).
function renderDataSources(root) {
  const copy = t();
  const node = section(null, copy.dataSources);

  node.appendChild(el("h3", null, copy.riigikoguApiTitle));
  const apiBody = el("p", null, `${copy.riigikoguApiBody} `);
  const apiLink = el("a", null, "api.riigikogu.ee");
  apiLink.href = "https://api.riigikogu.ee";
  apiBody.appendChild(apiLink);
  node.appendChild(apiBody);

  node.appendChild(el("h3", null, copy.documentsTitle));
  node.appendChild(el("p", null, copy.documentsBody));

  node.appendChild(el("h3", null, copy.refreshTitle));
  node.appendChild(el("p", null, copy.refreshBody));

  root.appendChild(node);
}

function renderModel(root, methodology) {
  const copy = t();
  const engine = methodology.engine || {};
  const sampling = engine.sampling || {};
  const node = section(null, copy.aiModel);

  const modelLine = engine.provider
    ? `${copy.model}: ${engine.model || "?"} (${engine.provider})`
    : `${copy.model}: ${engine.model || "?"}`;
  node.appendChild(el("p", null, modelLine));
  node.appendChild(el("p", null, copy.samplingLine(sampling)));

  node.appendChild(el("h3", null, copy.textLimitTitle));
  node.appendChild(el("p", null, copy.textLimitBody));

  root.appendChild(node);
}

function renderPipeline(root, methodology) {
  const copy = t();
  const node = section(null, copy.pipeline);
  const grid = el("div", "pipeline");
  (methodology.pipeline_order || []).forEach((step, index) => {
    const [title, body] = copy.pipelineText[step] || [step, ""];
    const card = el("div", "step");
    card.appendChild(el("span", "idx", String(index + 1)));
    card.appendChild(el("strong", null, title));
    card.appendChild(el("p", null, body));
    grid.appendChild(card);
  });
  node.appendChild(grid);
  root.appendChild(node);
}

function renderChecks(root, methodology) {
  const copy = t();
  const categories = categoryMap(methodology);
  const node = section(null, copy.checks);
  const wrap = el("div", "table-wrap");
  const table = el("table");
  table.id = "checks-table";
  const thead = el("thead");
  const headRow = el("tr");
  [copy.name, copy.description, copy.category, copy.enabled, copy.version].forEach((heading) => {
    headRow.appendChild(el("th", null, heading));
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const check of methodology.checks || []) {
    const row = el("tr", check.enabled ? "" : "disabled");
    row.dataset.checkId = check.id;
    row.appendChild(el("td", null, field(check, "name")));
    row.appendChild(el("td", null, field(check, "description")));
    row.appendChild(el("td", null, categories.get(check.category) || check.category));
    const status = el("span", `status${check.enabled ? "" : " off"}`, check.enabled ? copy.on : copy.off);
    const statusCell = el("td");
    statusCell.appendChild(status);
    row.appendChild(statusCell);
    row.appendChild(el("td", null, check.version || ""));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  node.appendChild(wrap);
  root.appendChild(node);
}

function renderPasses(root, methodology) {
  const copy = t();
  const node = section(null, copy.systemPrompts);
  const list = el("div", "passes");
  for (const pass of methodology.passes || []) {
    const card = el("article", "pass-card");
    card.dataset.passId = pass.id;
    card.appendChild(el("h3", null, field(pass, "name")));
    card.appendChild(el("p", "pass-meta", `${copy.version}: ${pass.version || ""} · ${copy.promptSha}: ${pass.prompt_sha || ""}`));
    card.appendChild(el("p", null, field(pass, "description")));

    const details = el("details", "prompt-detail");
    details.dataset.passId = pass.id;
    details.appendChild(el("summary", null, copy.showPrompt(pass.version || pass.id)));
    details.appendChild(el("h3", null, copy.systemPrompt));
    details.appendChild(el("pre", "system-prompt", pass.system_prompt || ""));
    details.appendChild(el("h3", null, copy.userTemplate));
    details.appendChild(el("pre", "user-template", pass.user_template || ""));
    card.appendChild(details);
    list.appendChild(card);
  }
  node.appendChild(list);
  root.appendChild(node);
}

function renderCategories(root, methodology) {
  const copy = t();
  const node = section(null, copy.categories);
  const wrap = el("div", "table-wrap");
  const table = el("table");
  table.id = "categories-table";
  const thead = el("thead");
  const headRow = el("tr");
  [copy.label, copy.honte].forEach((heading) => headRow.appendChild(el("th", null, heading)));
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = el("tbody");
  for (const category of methodology.categories || []) {
    const row = el("tr");
    row.dataset.category = category.key;
    row.appendChild(el("td", null, field(category, "label")));
    row.appendChild(el("td", null, category.honte_citation || ""));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  node.appendChild(wrap);

  const rules = el("div", "rules");
  for (const rule of methodology.honte_rules || []) {
    const details = el("details", "honte-rule");
    const summary = rule.citation || rule.honte_citation || rule.rule || rule.category || "HÕNTE";
    details.appendChild(el("summary", null, summary));
    details.appendChild(el("pre", null, ruleText(rule)));
    rules.appendChild(details);
  }
  if (rules.children.length) {
    const detailsTitle = el("h3", null, copy.honteRules);
    detailsTitle.style.marginTop = "18px";
    node.appendChild(detailsTitle);
    node.appendChild(rules);
  }
  root.appendChild(node);
}

function ruleText(rule) {
  if (typeof rule === "string") return rule;
  const localized = lang() === "en" ? rule.text_en : rule.text_et;
  if (localized) return localized;
  const text = rule.text || rule.description || rule.body;
  if (text) return text;
  return JSON.stringify(rule, null, 2);
}

function renderLimitations(root, methodology) {
  const copy = t();
  const node = section(null, copy.limitations);
  const list = el("ul", "limitations");
  const items = lang() === "en" ? methodology.limitations_en : methodology.limitations_et;
  for (const item of items || []) {
    list.appendChild(el("li", null, item));
  }
  node.appendChild(list);
  root.appendChild(node);
}

function renderData(root, methodology) {
  const copy = t();
  const api = methodology.data_api || {};
  const base = api.base || "";
  const node = section("andmed", copy.dataApi);
  node.appendChild(el("p", "api-note", lang() === "en" ? api.note_en : api.note_et));

  const chips = el("div", "chips");
  for (const table of api.tables || []) {
    chips.appendChild(el("code", "chip", table));
  }
  node.appendChild(el("h3", null, copy.tables));
  node.appendChild(chips);

  node.appendChild(el("h3", null, copy.examples));
  const examples = el("div", "curl-grid");
  [
    `curl '${base}/bill_index?select=*' \\\n  -H 'apikey: <publishable-key>'`,
    `curl '${base}/findings?select=*&analysis_id=eq.<analysis-id>' \\\n  -H 'apikey: <publishable-key>'`,
    `curl '${base}/analysis_samples?select=*&analysis_id=eq.<analysis-id>&order=sample_no.asc' \\\n  -H 'apikey: <publishable-key>'`
  ].forEach((command) => examples.appendChild(el("pre", "curl-example", command)));
  node.appendChild(examples);

  const repo = el("p");
  const link = el("a", null, copy.repo);
  link.href = "https://github.com/luukasilves/lawlab";
  repo.appendChild(link);
  node.appendChild(repo);

  node.appendChild(el("p", "gold-note", copy.gold));
  root.appendChild(node);
}

function init(methodology) {
  lastMethodology = methodology;
  const root = document.getElementById("metoodika-root");
  if (!root) return;
  document.documentElement.lang = lang();
  document.title = "About";
  clear(root);
  renderHero(root, methodology);
  renderStory(root, methodology);
  renderDataSources(root);
  renderModel(root, methodology);
  renderPasses(root, methodology);
  renderPipeline(root, methodology);
  renderChecks(root, methodology);
  renderCategories(root, methodology);
  renderLimitations(root, methodology);
  renderDownloads(root);
  renderData(root, methodology);
}

function rerender() {
  if (lastMethodology) init(lastMethodology);
}

function showError(error) {
  const root = document.getElementById("metoodika-root");
  if (!root) return;
  clear(root);
  const box = el("div", "error", `${t().loadError} ${error?.message || error || ""}`);
  root.appendChild(box);
}

async function autoInit() {
  await moduleReady;
  if (lastMethodology || !document.getElementById("metoodika-root")) return;
  try {
    const response = await fetch("/data/methodology.json");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    init(await response.json());
  } catch (error) {
    showError(error);
  }
}

window.LawlabMetoodika = { init, rerender, ready: moduleReady };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoInit, { once: true });
} else {
  autoInit();
}
