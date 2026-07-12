import {
  fetchAnalysisWithFindings,
  fetchBill,
  fetchHistory,
  fetchParsedText,
  fetchSampleRaw,
  fetchSamplesMeta,
  postFeedback
} from "api.js";
import { t as translate } from "i18n.js";

const SEVERITY_RANK = { HIGH: 3, MEDIUM: 2, LOW: 1 };
const SEVERITIES = new Set(["HIGH", "MEDIUM", "LOW"]);

const FALLBACKS = {
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
  history: "Ajalugu",
  independent_analyses: "sõltumatut analüüsi",
  meta_committee: "Juhtivkomisjon",
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
  skeptic_refuted: "Ümber lükatud",
  skeptic_step: "Skeptiku kontroll",
  skeptic_upheld: "Kontrollitud",
  source_model: "Mudel",
  source_rule: "Reegel",
  suggestion: "Soovitus",
  threshold: "künnis",
  tokens: "Tokenid",
  totals_step: "Kokkuvõte",
  view_riigikogu: "Vaata Riigikogu veebis",
  zero_findings: "Avaldatavaid leide ei tuvastatud."
};

let state = {
  analysis: null,
  bill: null,
  config: {},
  currentHistory: null,
  document: null,
  history: [],
  methodology: emptyMethodology(),
  parsedText: "",
  samplesMeta: []
};
let docClicksBound = false;

function tr(key, fallback = key) {
  try {
    const value = translate(key);
    if (value && value !== key) {
      return String(value);
    }
  } catch {
    return fallback;
  }
  return FALLBACKS[key] || fallback;
}

function byId(id) {
  return document.getElementById(id);
}

function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function text(value) {
  return document.createTextNode(value == null ? "" : String(value));
}

function appendText(node, value) {
  node.appendChild(text(value));
}

function span(className, value) {
  const node = document.createElement("span");
  if (className) {
    node.className = className;
  }
  node.textContent = value == null ? "" : String(value);
  return node;
}

function div(className) {
  const node = document.createElement("div");
  if (className) {
    node.className = className;
  }
  return node;
}

function safeSeverity(severity) {
  const value = String(severity || "").toUpperCase();
  return SEVERITIES.has(value) ? value : "LOW";
}

function severityRank(severity) {
  return SEVERITY_RANK[safeSeverity(severity)] || 0;
}

function isRefuted(finding) {
  return finding?.skeptic_verdict === "refuted";
}

function getAnalysisId(analysis = state.analysis) {
  return analysis?.id || analysis?.analysis_id || "";
}

function getHistoryAnalysisId(row) {
  return row?.analysis_id || row?.id || "";
}

function getFindings(analysis = state.analysis) {
  return Array.isArray(analysis?.findings) ? analysis.findings : [];
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("et-EE", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function formatSeconds(ms) {
  const num = Number(ms || 0) / 1000;
  return `${num.toFixed(num >= 10 ? 0 : 1)} s`;
}

function formatMoney(value) {
  const num = Number(value || 0);
  return `$${num.toFixed(num >= 1 ? 2 : 4)}`;
}

function formatTokens(input, output) {
  const total = Number(input || 0) + Number(output || 0);
  return total ? new Intl.NumberFormat("et-EE").format(total) : "-";
}

function sortFindings(findings) {
  return findings.slice().sort((a, b) => {
    const severityDiff = severityRank(b.severity) - severityRank(a.severity);
    if (severityDiff) {
      return severityDiff;
    }
    const confidenceDiff = Number(b.confidence || 0) - Number(a.confidence || 0);
    if (confidenceDiff) {
      return confidenceDiff;
    }
    return String(a.title || a.id || "").localeCompare(String(b.title || b.id || ""), "et");
  });
}

function emptyMethodology() {
  return {
    categoriesByKey: new Map(),
    checksById: new Map(),
    passesById: new Map()
  };
}

async function loadMethodology() {
  try {
    const response = await fetch("/data/methodology.json");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    const methodology = emptyMethodology();
    for (const category of data.categories || []) {
      methodology.categoriesByKey.set(category.key, category);
    }
    for (const check of data.checks || []) {
      methodology.checksById.set(check.id, check);
    }
    for (const pass of data.passes || []) {
      methodology.passesById.set(pass.id, pass);
    }
    return methodology;
  } catch {
    return emptyMethodology();
  }
}

function localizedName(item, rawKey) {
  if (!item) {
    return rawKey || "-";
  }
  const lang = document.documentElement.lang || "et";
  if (lang.startsWith("en")) {
    return item.name_en || item.label_en || item.name_et || item.label_et || rawKey || "-";
  }
  return item.name_et || item.label_et || item.name_en || item.label_en || rawKey || "-";
}

function categoryLabel(categoryKey) {
  const item = state.methodology.categoriesByKey.get(categoryKey);
  return localizedName(item, categoryKey);
}

function categoryCitation(categoryKey) {
  return state.methodology.categoriesByKey.get(categoryKey)?.honte_citation || "";
}

function checkLabel(checkId) {
  const item = state.methodology.checksById.get(checkId);
  return localizedName(item, checkId);
}

function normalizeParsedText(parsedText) {
  if (typeof parsedText === "string") {
    return parsedText;
  }
  return parsedText?.parsed_text || parsedText?.text || "";
}

function billDocuments(bill) {
  return bill?.bill_documents || bill?.documents || [];
}

function documentVersion(documentRow) {
  return documentRow?.doc_version || documentRow?.version || documentRow?.version_id || "";
}

function documentId(documentRow) {
  return documentRow?.id || documentRow?.document_id || "";
}

function findAnalysedDocument(bill, analysis, historyRow) {
  const docs = billDocuments(bill);
  const wantedVersion = historyRow?.doc_version || analysis?.doc_version || "";
  const wantedDocumentId = analysis?.document_id || historyRow?.document_id || "";
  if (wantedDocumentId) {
    const byDocumentId = docs.find((doc) => documentId(doc) === wantedDocumentId);
    if (byDocumentId) {
      return byDocumentId;
    }
  }
  if (wantedVersion) {
    const byVersion = docs.find((doc) => documentVersion(doc) === wantedVersion);
    if (byVersion) {
      return byVersion;
    }
  }
  return docs[0] || null;
}

function sortedHistory(history) {
  return (history || []).slice().sort((a, b) => {
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  });
}

function currentHistoryFor(history, analysis) {
  const analysisId = getAnalysisId(analysis);
  return history.find((row) => getHistoryAnalysisId(row) === analysisId) || history[0] || null;
}

function setFrame() {
  const bill = state.bill || {};
  const apiData = bill.api_data || {};
  const titleParts = [bill.bill_number, bill.title].filter(Boolean);
  const pageTitle = titleParts.join(" ") || "Apsakaleidja";
  byId("billTitle").textContent = pageTitle;
  document.title = pageTitle;

  const backLink = byId("backLink");
  backLink.textContent = `< ${tr("back")}`;

  const riigikoguLink = byId("riigikoguLink");
  if (apiData.uuid) {
    riigikoguLink.hidden = false;
    riigikoguLink.href = `https://www.riigikogu.ee/tegevus/eelnoud/eelnou/${encodeURIComponent(apiData.uuid)}`;
    riigikoguLink.textContent = tr("view_riigikogu");
  } else {
    riigikoguLink.hidden = true;
    riigikoguLink.removeAttribute("href");
    riigikoguLink.textContent = "";
  }

  renderMetaGrid();
}

function renderMetaGrid() {
  const grid = byId("metaGrid");
  clear(grid);
  const apiData = state.bill?.api_data || {};
  const cards = [
    [tr("meta_type"), apiData.draftTypeCode || "-"],
    [tr("meta_committee"), apiData.leadingCommittee?.name || "-"],
    [tr("meta_updated"), formatDate(state.document?.fetched_at)]
  ];
  for (const [label, value] of cards) {
    const card = div("meta-card");
    card.appendChild(span("meta-label", label));
    card.appendChild(span("meta-value", value));
    grid.appendChild(card);
  }
}

function renderAnalysis() {
  const allFindings = getFindings();
  const visibleFindings = sortFindings(allFindings.filter((finding) => !isRefuted(finding)));
  const refutedFindings = sortFindings(allFindings.filter(isRefuted));

  byId("resultsTitle").textContent = tr("results");
  byId("resultsCount").textContent = String(visibleFindings.length);

  renderDocumentHighlights(state.parsedText, visibleFindings);
  renderFindingsList(visibleFindings);
  renderRefutedSection(refutedFindings);
  renderPipeline();
  renderHistory();
  renderRawJsonPanel();
  renderMetaGrid();
}

function renderDocumentHighlights(parsedText, visibleFindings) {
  const container = byId("docText");
  clear(container);
  const fullText = parsedText || "";
  const ranges = visibleFindings
    .map((finding) => {
      const start = Number(finding.char_start);
      const end = Number(finding.char_end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
        return null;
      }
      return {
        end: Math.min(fullText.length, Math.max(0, end)),
        finding,
        id: String(finding.id),
        start: Math.min(fullText.length, Math.max(0, start))
      };
    })
    .filter((range) => range && range.end > range.start);

  if (!ranges.length) {
    container.appendChild(text(fullText));
    return;
  }

  const boundaries = Array.from(new Set(ranges.flatMap((range) => [range.start, range.end])))
    .filter((offset) => offset >= 0 && offset <= fullText.length)
    .sort((a, b) => a - b);
  const anchored = new Set();
  let cursor = 0;

  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    if (start > cursor) {
      container.appendChild(text(fullText.slice(cursor, start)));
    }

    const coverers = ranges.filter((range) => range.start <= start && range.end >= end);
    if (coverers.length) {
      const maxSeverity = coverers.reduce((best, range) => {
        return severityRank(range.finding.severity) > severityRank(best) ? safeSeverity(range.finding.severity) : best;
      }, "LOW");
      const mark = document.createElement("mark");
      mark.classList.add(maxSeverity);
      mark.dataset.findings = coverers.map((range) => range.id).join(" ");

      const firstCoverers = coverers.filter((range) => !anchored.has(range.id));
      if (firstCoverers.length) {
        const [primary, ...secondary] = firstCoverers;
        mark.id = `mark-${primary.id}`;
        anchored.add(primary.id);
        for (const range of secondary) {
          const anchor = document.createElement("span");
          anchor.className = "mark-anchor";
          anchor.id = `mark-${range.id}`;
          mark.appendChild(anchor);
          anchored.add(range.id);
        }
      }
      mark.appendChild(text(fullText.slice(start, end)));
      container.appendChild(mark);
    } else {
      container.appendChild(text(fullText.slice(start, end)));
    }
    cursor = end;
  }

  if (cursor < fullText.length) {
    container.appendChild(text(fullText.slice(cursor)));
  }
}

function renderFindingsList(findings) {
  const list = byId("findingsList");
  clear(list);
  if (!findings.length) {
    const empty = div("empty-panel");
    empty.textContent = tr("zero_findings");
    list.appendChild(empty);
    return;
  }
  for (const finding of findings) {
    list.appendChild(renderFindingCard(finding, { refuted: false }));
  }
}

function renderRefutedSection(findings) {
  const section = byId("refutedSection");
  clear(section);
  if (!findings.length) {
    return;
  }
  const wrapper = div("refuted-block");
  const heading = div("refuted-heading");
  const h3 = document.createElement("h3");
  h3.textContent = tr("refuted_section");
  heading.appendChild(h3);
  heading.appendChild(span("badge skeptic-refuted", String(findings.length)));
  wrapper.appendChild(heading);
  for (const finding of findings) {
    wrapper.appendChild(renderFindingCard(finding, { refuted: true }));
  }
  section.appendChild(wrapper);
}

function renderFindingCard(finding, options) {
  const card = div(options.refuted ? "finding-card refuted" : "finding-card");
  card.id = `finding-${finding.id}`;
  card.dataset.findingId = String(finding.id);

  const top = div("card-topline");
  top.appendChild(span(`badge severity ${safeSeverity(finding.severity)}`, safeSeverity(finding.severity)));
  top.appendChild(span("badge", categoryLabel(finding.category)));
  top.appendChild(sourceBadge(finding.source));
  const agreement = agreementBadge(finding);
  if (agreement) {
    top.appendChild(agreement);
  }
  const skeptic = skepticBadge(finding);
  if (skeptic) {
    top.appendChild(skeptic);
  }
  card.appendChild(top);

  const title = div("finding-title");
  title.textContent = finding.title || "-";
  card.appendChild(title);

  const subline = div("finding-subline");
  appendText(subline, finding.location || finding.provision_id || "-");
  if (finding.honte_rule) {
    subline.appendChild(honteChip(finding));
  }
  card.appendChild(subline);

  card.appendChild(renderDetails(finding, options.refuted));

  if (!options.refuted) {
    card.appendChild(renderFeedback(finding));
    card.addEventListener("click", (event) => {
      if (event.target.closest("button") || event.target.closest("summary")) {
        return;
      }
      selectFindings([String(finding.id)], { fromCard: true });
    });
  }

  return card;
}

function sourceBadge(source) {
  if (source === "deterministic") {
    return span("badge source-rule", tr("source_rule"));
  }
  return span("badge source-model", tr("source_model"));
}

function agreementBadge(finding) {
  if (!finding.runs_total) {
    return null;
  }
  return span("badge", `${tr("agreement")}: ${finding.runs_found || 0}/${finding.runs_total}`);
}

function skepticBadge(finding) {
  if (finding.skeptic_verdict === "upheld") {
    return span("badge skeptic-upheld", tr("skeptic_upheld"));
  }
  if (finding.skeptic_verdict === "refuted") {
    return span("badge skeptic-refuted", tr("skeptic_refuted"));
  }
  return null;
}

function honteChip(finding) {
  const chip = span("honte-chip", finding.honte_rule);
  chip.title = categoryCitation(finding.category) || finding.honte_rule || "";
  return chip;
}

function renderDetails(finding, refuted) {
  const details = document.createElement("details");
  details.className = "finding-details";
  const summary = document.createElement("summary");
  summary.textContent = tr("reasoning");
  details.appendChild(summary);

  appendDetail(details, tr("description"), finding.description);
  appendDetail(details, tr("reasoning"), finding.reasoning);
  appendDetail(details, tr("suggestion"), finding.suggestion);

  if (finding.evidence_quote) {
    const quote = div("quote-block");
    quote.textContent = finding.evidence_quote;
    details.appendChild(quote);
  }

  if (refuted && finding.skeptic_reasoning) {
    const block = div("detail-block");
    block.textContent = finding.skeptic_reasoning;
    details.appendChild(block);
  }

  return details;
}

function appendDetail(parent, label, value) {
  if (!value) {
    return;
  }
  const block = div("detail-block");
  const labelNode = span("detail-label", `${label}: `);
  block.appendChild(labelNode);
  appendText(block, value);
  parent.appendChild(block);
}

function renderFeedback(finding) {
  const row = div("feedback-row");
  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.dataset.feedback = "confirm";
  confirm.textContent = tr("confirm");
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.dataset.feedback = "dismiss";
  dismiss.textContent = tr("dismiss");
  const message = span("feedback-message", "");

  confirm.addEventListener("click", (event) => {
    event.stopPropagation();
    handleFeedback(finding.id, "confirm", row);
  });
  dismiss.addEventListener("click", (event) => {
    event.stopPropagation();
    handleFeedback(finding.id, "dismiss", row);
  });

  row.append(confirm, dismiss, message);
  return row;
}

async function handleFeedback(findingId, verdict, row) {
  const message = row.querySelector(".feedback-message");
  if (message) {
    message.textContent = "";
    message.classList.remove("error-text");
  }
  try {
    const response = await postFeedback(findingId, verdict);
    const status = typeof response?.status === "number" ? response.status : 201;
    if (status !== 201) {
      throw new Error(`HTTP ${status}`);
    }
    clear(row);
    row.appendChild(span("feedback-message", tr("feedback_thanks")));
  } catch {
    if (message) {
      message.textContent = tr("feedback_error");
      message.classList.add("error-text");
    }
  }
}

function getAnchorForFinding(findingId) {
  const anchor = document.getElementById(`mark-${findingId}`);
  return anchor?.closest("mark") || anchor;
}

function selectFindings(findingIds, options = {}) {
  const ids = findingIds.map(String).filter(Boolean);
  document.querySelectorAll(".finding-card.active, mark.active").forEach((node) => {
    node.classList.remove("active");
  });

  for (const id of ids) {
    const card = document.getElementById(`finding-${id}`);
    if (card) {
      card.classList.add("active");
    }
    const mark = getAnchorForFinding(id);
    if (mark) {
      mark.classList.add("active");
    }
  }

  if (options.fromCard && ids.length) {
    const mark = getAnchorForFinding(ids[0]);
    if (mark) {
      mark.classList.add("focus");
      mark.scrollIntoView({ block: "center", behavior: "smooth" });
      window.setTimeout(() => mark.classList.remove("focus"), 1200);
    }
  }

  if (options.fromMark && ids.length) {
    const card = document.getElementById(`finding-${ids[0]}`);
    if (card) {
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }
}

function renderPipeline() {
  const panelHost = byId("pipelinePanel");
  clear(panelHost);
  const details = document.createElement("details");
  details.className = "info-panel";
  const summary = document.createElement("summary");
  summary.textContent = tr("pipeline");
  details.appendChild(summary);

  const flow = document.createElement("ol");
  flow.className = "pipeline-flow";
  flow.appendChild(pipelineDeterministicStep());
  flow.appendChild(pipelineSamplingStep());
  flow.appendChild(pipelineClusteringStep());
  flow.appendChild(pipelineSkepticStep());
  flow.appendChild(pipelineTotalsStep());
  details.appendChild(flow);
  panelHost.appendChild(details);
}

function pipelineStep(title) {
  const step = document.createElement("li");
  step.className = "pipeline-step";
  const heading = document.createElement("h4");
  heading.textContent = title;
  step.appendChild(heading);
  return step;
}

function pipelineDeterministicStep() {
  const step = pipelineStep(tr("deterministic_step"));
  const checks = engineChecks();
  const deterministicCount = getFindings().filter((finding) => {
    return finding.source === "deterministic" && !isRefuted(finding);
  }).length;
  const list = document.createElement("ul");
  list.className = "small-list";
  if (checks.length) {
    for (const check of checks) {
      const item = document.createElement("li");
      item.textContent = `${checkLabel(check.id)}${check.version ? ` ${check.version}` : ""}`;
      list.appendChild(item);
    }
  } else {
    const item = document.createElement("li");
    item.textContent = tr("no_data");
    list.appendChild(item);
  }
  const count = document.createElement("p");
  count.className = "detail-block";
  count.textContent = `${deterministicCount} ${tr("deterministic_count")}`;
  step.append(list, count);
  return step;
}

function engineChecks() {
  const checks = state.analysis?.engine?.checks || [];
  if (checks.length) {
    return checks.map((entry) => {
      if (Array.isArray(entry)) {
        return { id: entry[0], version: entry[1] };
      }
      return { id: entry.id, version: entry.version || entry.ver };
    }).filter((entry) => entry.id);
  }
  const ids = new Set(getFindings()
    .filter((finding) => finding.source === "deterministic" && finding.check_id)
    .map((finding) => finding.check_id));
  return Array.from(ids).map((id) => ({ id, version: "" }));
}

function pipelineSamplingStep() {
  const step = pipelineStep(tr("sampling_step"));
  const params = state.analysis?.engine?.params || state.analysis?.config || {};
  const interpretiveSamples = samplesForInterpretivePass();
  const sampleCount = Number(params.samples || params.n || interpretiveSamples.length || 0);
  const threshold = Number(params.k || params.min_agreement || 0);
  const intro = document.createElement("p");
  intro.className = "detail-block";
  intro.textContent = `${sampleCount} ${tr("independent_analyses")}, ${tr("threshold")} ${threshold || "-"}`;
  step.appendChild(intro);
  step.appendChild(renderSampleTable(interpretiveSamples));
  return step;
}

function samplesForInterpretivePass() {
  return (state.samplesMeta || []).filter((sample) => {
    const passId = String(sample.pass_id || "").toLowerCase();
    return !passId.includes("refute") && !passId.includes("skeptic");
  });
}

function renderSampleTable(samples) {
  const table = document.createElement("table");
  table.className = "sample-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["#", tr("returned"), tr("grounded"), tr("dropped"), tr("tokens"), tr("cost")]) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  if (!samples.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = tr("no_data");
    row.appendChild(cell);
    tbody.appendChild(row);
  }

  for (const sample of samples) {
    const row = document.createElement("tr");
    row.className = "sample-row";
    row.dataset.sampleId = sample.id;
    row.tabIndex = 0;
    row.addEventListener("click", () => showSampleRaw(row, sample));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showSampleRaw(row, sample);
      }
    });

    const indexCell = document.createElement("td");
    appendText(indexCell, sample.sample_idx ?? "-");
    if (sample.reused) {
      indexCell.appendChild(text(" "));
      indexCell.appendChild(span("badge", tr("sample_reused")));
    }
    row.appendChild(indexCell);
    row.appendChild(sampleCell(sample.returned_count));
    row.appendChild(sampleCell(sample.grounded_count));
    row.appendChild(sampleCell(sample.dropped_ungrounded));
    row.appendChild(sampleCell(formatTokens(sample.input_tokens, sample.output_tokens)));
    row.appendChild(sampleCell(formatMoney(sample.cost_usd)));
    tbody.appendChild(row);
  }

  table.appendChild(tbody);
  return table;
}

function sampleCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value == null || value === "" ? "-" : String(value);
  return cell;
}

async function showSampleRaw(row, sample) {
  const next = row.nextElementSibling;
  if (next?.classList.contains("raw-sample-row") && next.dataset.sampleId === String(sample.id)) {
    next.hidden = !next.hidden;
    return;
  }

  const rawRow = document.createElement("tr");
  rawRow.className = "raw-sample-row";
  rawRow.dataset.sampleId = String(sample.id);
  const cell = document.createElement("td");
  cell.colSpan = row.children.length;
  cell.textContent = tr("no_data");
  rawRow.appendChild(cell);
  row.after(rawRow);

  try {
    cell.textContent = "";
    const data = await fetchSampleRaw(sample.id);
    const pre = document.createElement("pre");
    pre.className = "raw-output";
    const parsed = data?.parsed == null ? "" : `\n\n${JSON.stringify(data.parsed, null, 2)}`;
    pre.textContent = `${data?.raw_output || ""}${parsed}`;
    cell.appendChild(pre);
  } catch {
    cell.textContent = tr("feedback_error");
    cell.className = "error-text";
  }
}

function pipelineClusteringStep() {
  const step = pipelineStep(tr("clustering_step"));
  const clusters = state.analysis?.stats?.llm?.clusters || [];
  const list = document.createElement("ul");
  list.className = "small-list";
  if (!clusters.length) {
    const item = document.createElement("li");
    item.textContent = tr("no_data");
    list.appendChild(item);
  }
  for (const cluster of clusters) {
    const item = document.createElement("li");
    const label = cluster.title || categoryLabel(cluster.category) || "-";
    const outcome = cluster.kept ? tr("cluster_published") : tr("cluster_below");
    item.textContent = `${label}: ${tr("found")} ${cluster.support || 0}/${cluster.n || 0} -> ${outcome}`;
    list.appendChild(item);
  }
  step.appendChild(list);
  return step;
}

function pipelineSkepticStep() {
  const step = pipelineStep(tr("skeptic_step"));
  const refute = state.analysis?.stats?.refute || {};
  const line = document.createElement("p");
  line.className = "detail-block";
  line.textContent = `${tr("checked")} ${refute.judged || 0}, ${tr("refuted")} ${refute.refuted || 0}`;
  step.appendChild(line);
  return step;
}

function pipelineTotalsStep() {
  const step = pipelineStep(tr("totals_step"));
  const list = document.createElement("ul");
  list.className = "small-list";
  const totals = [
    [tr("duration"), formatSeconds(state.analysis?.duration_ms)],
    [tr("tokens"), formatTokens(state.analysis?.input_tokens, state.analysis?.output_tokens)],
    [tr("cost"), formatMoney(state.analysis?.cost_usd)]
  ];
  for (const [label, value] of totals) {
    const item = document.createElement("li");
    item.textContent = `${label}: ${value}`;
    list.appendChild(item);
  }
  step.appendChild(list);
  return step;
}

function renderHistory() {
  const host = byId("historyPanel");
  clear(host);
  const details = document.createElement("details");
  details.className = "info-panel history-panel";
  const summary = document.createElement("summary");
  summary.textContent = tr("history");
  details.appendChild(summary);

  const list = div("history-list");
  for (const row of state.history) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-row";
    const analysisId = getHistoryAnalysisId(row);
    button.dataset.analysisId = analysisId;
    if (analysisId === getAnalysisId()) {
      button.classList.add("current");
    }

    const main = div("history-main");
    main.textContent = formatDate(row.created_at);
    const meta = div("history-meta");
    meta.textContent = [
      row.prompt_version,
      row.model,
      row.doc_version,
      `${row.finding_count ?? 0} ${tr("finding_count")}`,
      `${row.refuted_count ?? 0} ${tr("refuted")}`
    ].filter(Boolean).join(" · ");
    button.append(main, meta);
    button.addEventListener("click", () => switchAnalysis(analysisId));
    list.appendChild(button);
  }
  if (!state.history.length) {
    const empty = div("empty-panel");
    empty.textContent = tr("no_data");
    list.appendChild(empty);
  }

  details.appendChild(list);
  host.appendChild(details);
}

async function switchAnalysis(analysisId) {
  if (!analysisId || analysisId === getAnalysisId()) {
    return;
  }
  const historyRow = state.history.find((row) => getHistoryAnalysisId(row) === analysisId) || null;
  const analysis = await fetchAnalysisWithFindings(analysisId);
  const samplesMeta = await fetchSamplesMeta(analysisId).catch(() => []);
  const doc = findAnalysedDocument(state.bill, analysis, historyRow);
  let parsedText = state.parsedText;
  if (doc && documentId(doc) && documentId(doc) !== documentId(state.document)) {
    parsedText = normalizeParsedText(await fetchParsedText(documentId(doc)).catch(() => parsedText));
  }
  state = {
    ...state,
    analysis,
    currentHistory: historyRow,
    document: doc || state.document,
    parsedText,
    samplesMeta
  };
  renderAnalysis();
}

function renderRawJsonPanel() {
  const host = byId("rawJsonPanel");
  clear(host);
  const details = document.createElement("details");
  details.className = "info-panel raw-json-panel";
  const summary = document.createElement("summary");
  summary.textContent = tr("raw_json");
  details.appendChild(summary);

  const note = document.createElement("p");
  note.className = "detail-block";
  appendText(note, tr("raw_json_note"));
  note.appendChild(text(" "));
  const link = document.createElement("a");
  link.href = "/metoodika#andmed";
  link.textContent = tr("methodology_data");
  note.appendChild(link);
  details.appendChild(note);

  for (const url of rawJsonUrls()) {
    details.appendChild(copyableCode(url));
  }

  host.appendChild(details);
}

function rawJsonUrls() {
  const base = supabaseUrl();
  const analysisId = encodeURIComponent(getAnalysisId());
  const billId = encodeURIComponent(state.bill?.id || state.bill?.bill_id || "");
  const urls = [];
  if (analysisId) {
    urls.push(`${base}/rest/v1/analyses?id=eq.${analysisId}&select=*,findings(*)`);
    urls.push(`${base}/rest/v1/analysis_samples?analysis_id=eq.${analysisId}&select=*`);
  }
  if (billId) {
    urls.push(`${base}/rest/v1/analysis_history?bill_id=eq.${billId}&select=*`);
  }
  return urls;
}

function supabaseUrl() {
  const value = state.config?.SUPABASE_URL
    || state.config?.supabaseUrl
    || window.LawlabConfig?.SUPABASE_URL
    || window.SUPABASE_URL
    || "";
  return String(value).replace(/\/$/, "");
}

function copyableCode(value) {
  const code = document.createElement("code");
  code.className = "copyable";
  code.tabIndex = 0;
  code.textContent = value;
  code.addEventListener("click", async () => {
    try {
      await navigator.clipboard?.writeText(value);
    } catch {
      code.focus();
    }
  });
  return code;
}

function bindDocumentClicks() {
  const container = byId("docText");
  if (!container || docClicksBound) {
    return;
  }
  docClicksBound = true;
  container.addEventListener("click", (event) => {
    const mark = event.target.closest("mark[data-findings]");
    if (!mark) {
      return;
    }
    selectFindings(mark.dataset.findings.split(/\s+/), { fromMark: true });
  });
}

async function init(data) {
  bindDocumentClicks();
  const history = sortedHistory(data.history || []);
  const analysis = data.analysis || null;
  const currentHistory = currentHistoryFor(history, analysis);
  const documentRow = data.document || findAnalysedDocument(data.bill, analysis, currentHistory);
  state = {
    analysis,
    bill: data.bill || {},
    config: data.config || {},
    currentHistory,
    document: documentRow,
    history,
    methodology: await loadMethodology(),
    parsedText: normalizeParsedText(data.parsedText),
    samplesMeta: data.samplesMeta || []
  };
  setFrame();
  renderAnalysis();
  return state;
}

function resolveBillId(locationLike = window.location) {
  const params = new URLSearchParams(locationLike.search || "");
  const queryId = params.get("id");
  if (queryId) {
    return queryId;
  }
  const match = (locationLike.pathname || "").match(/\/bill\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function autoInit() {
  try {
    const billId = resolveBillId();
    if (!billId) {
      throw new Error(tr("no_data"));
    }
    const bill = await fetchBill(billId);
    const history = sortedHistory(await fetchHistory(billId));
    const currentHistory = history[0] || null;
    const analysisId = getHistoryAnalysisId(currentHistory);
    const analysis = analysisId ? await fetchAnalysisWithFindings(analysisId) : { findings: [] };
    const doc = findAnalysedDocument(bill, analysis, currentHistory);
    const parsedText = doc && documentId(doc) ? await fetchParsedText(documentId(doc)) : { parsed_text: "" };
    const samplesMeta = analysisId ? await fetchSamplesMeta(analysisId).catch(() => []) : [];
    await init({ analysis, bill, document: doc, history, parsedText, samplesMeta });
  } catch (error) {
    console.error("bill page init failed:", error);
    const app = byId("billApp");
    if (app) {
      clear(app);
      const node = div("app-error");
      node.textContent = `${tr("feedback_error")}: ${error.message || error}`;
      app.appendChild(node);
    }
  }
}

bindDocumentClicks();

window.LawlabBill = {
  init,
  resolveBillId
};

if (!window.__LAWLAB_TEST__) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoInit, { once: true });
  } else {
    autoInit();
  }
}

export { init, resolveBillId };
