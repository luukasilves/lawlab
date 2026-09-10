import { fetchBillIndex } from "./api.js";
import { t, applyStatic, withLang } from "./i18n.js";

const PAGE_SIZE = 25;
const SEARCH_DELAY_MS = 150;
const NO_TEXT_STATUSES = new Set([
  "no_files",
  "unsupported_format",
  "image_only_pdf",
  "empty_text",
  "download_failed",
  "convert_failed",
]);

let renderHeader = null;
let renderFooter = null;

let state = {
  rows: [],
  statFilter: null,
  search: "",
  status: "all",
  page: 1,
  searchTimer: null,
};

let els = {};

function byId(id) {
  return document.getElementById(id);
}

function asNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function rowFindingTotal(row) {
  return asNumber(row.high_count) + asNumber(row.medium_count) + asNumber(row.low_count);
}

function hasAnalysis(row) {
  return row.analysis_id != null;
}

function hasDocument(row) {
  return row.document_id != null;
}

function parseTime(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : 0;
}

function normalize(value) {
  return String(value ?? "").toLocaleLowerCase("et");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDateTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const pad = (part) => String(part).padStart(2, "0");
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function activityDate(row) {
  const value = row?.active_stage_date || row?.initiated_date || "";
  return String(value).slice(0, 10);
}

export function formatDay(ymd) {
  const value = String(ymd ?? "");
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return "";

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const isLeapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthDays = [31, isLeapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > monthDays[month - 1]) return "";

  return `${match[3]}.${match[2]}.${match[1]}`;
}

export function needsRecheck(row) {
  if (!hasDocument(row)) return false;
  const movedAt = activityDate(row);
  const checkedAt = String(row?.text_checked_at || row?.doc_fetched_at || "").slice(0, 10);
  return Boolean(movedAt && checkedAt && movedAt > checkedAt);
}

export function sortedRowsFor(rows) {
  return (Array.isArray(rows) ? rows.slice() : []).sort((left, right) => {
    const leftActivity = activityDate(left);
    const rightActivity = activityDate(right);
    if (leftActivity !== rightActivity) {
      if (!leftActivity) return 1;
      if (!rightActivity) return -1;
      return rightActivity.localeCompare(leftActivity);
    }

    const byFetchedAt = parseTime(right.doc_fetched_at) - parseTime(left.doc_fetched_at);
    if (byFetchedAt !== 0) return byFetchedAt;
    return String(left.bill_number ?? "").localeCompare(String(right.bill_number ?? ""), "et");
  });
}

function collectElements() {
  els = {
    root: byId("lawlab-index"),
    shellHeader: byId("app-shell-header"),
    shellFooter: byId("app-shell-footer"),
    statCards: byId("stat-cards"),
    search: byId("index-search"),
    status: byId("status-filter"),
    table: byId("bill-table"),
    tbody: document.querySelector("#bill-table tbody"),
    empty: byId("empty-state"),
    pagination: byId("pagination"),
  };
}

function mountShell(target, renderer) {
  if (!target || typeof renderer !== "function") return;

  const rendered = renderer(target);
  if (typeof rendered === "string") {
    target.innerHTML = rendered;
  } else if (rendered instanceof Node && rendered !== target) {
    target.replaceChildren(rendered);
  }
}

function setupStaticText() {
  if (els.search) {
    els.search.placeholder = t("search_ph");
    els.search.setAttribute("aria-label", t("search_ph"));
  }

  const headings = {
    number: "th_number",
    title: "th_title",
    status: "th_status",
    changed: "th_changed",
    findings: "th_findings",
  };

  Object.entries(headings).forEach(([column, key]) => {
    const heading = document.querySelector(`[data-column="${column}"]`);
    if (heading) heading.textContent = t(key);
  });

  applyStatic?.(document);
}

function bindEvents() {
  if (!els.root || els.root.dataset.lawlabIndexBound === "true") return;

  els.statCards?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-filter-card]");
    if (!card) return;

    const filter = card.dataset.filterCard;
    state.statFilter = filter === "total" || state.statFilter === filter ? null : filter;
    state.page = 1;
    renderStats();
    renderTable();
  });

  els.search?.addEventListener("input", (event) => {
    window.clearTimeout(state.searchTimer);
    const nextSearch = event.target.value;
    state.searchTimer = window.setTimeout(() => {
      state.search = nextSearch;
      state.page = 1;
      renderTable();
    }, SEARCH_DELAY_MS);
  });

  els.status?.addEventListener("change", (event) => {
    state.status = event.target.value;
    state.page = 1;
    renderTable();
  });

  els.pagination?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-page]");
    if (!button) return;
    state.page = asNumber(button.dataset.page) || 1;
    renderTable();
  });

  els.tbody?.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    const row = event.target.closest("tr[data-href]");
    if (row?.dataset.href) window.location.href = row.dataset.href;
  });

  els.tbody?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest("tr[data-href]");
    if (!row?.dataset.href) return;
    event.preventDefault();
    window.location.href = row.dataset.href;
  });

  els.root.dataset.lawlabIndexBound = "true";
}

function sortedRows() {
  return sortedRowsFor(state.rows);
}

function rowMatchesStat(row) {
  if (!state.statFilter) return true;
  if (state.statFilter === "high") return asNumber(row.high_count) > 0;
  if (state.statFilter === "medium") return asNumber(row.medium_count) > 0;
  if (state.statFilter === "low") return asNumber(row.low_count) > 0;
  return true;
}

function rowMatchesSearch(row) {
  const query = normalize(state.search).trim();
  if (!query) return true;
  return normalize(`${row.bill_number ?? ""} ${row.title ?? ""}`).includes(query);
}

function rowMatchesStatus(row) {
  if (state.status === "all") return true;
  return (row.active_stage || "") === state.status;
}

function filteredRows() {
  return sortedRows().filter((row) => rowMatchesStat(row) && rowMatchesSearch(row) && rowMatchesStatus(row));
}

function stats() {
  return {
    total: state.rows.length,
    analyzed: state.rows.filter(hasAnalysis).length,
    noText: state.rows.filter((row) => !hasDocument(row)).length,
    high: state.rows.filter((row) => asNumber(row.high_count) > 0).length,
    medium: state.rows.filter((row) => asNumber(row.medium_count) > 0).length,
    low: state.rows.filter((row) => asNumber(row.low_count) > 0).length,
  };
}

function renderStats() {
  if (!els.statCards) return;
  const counts = stats();
  const totalSub = `${counts.analyzed} ${t("stat_analyzed_sub")}${counts.noText > 0 ? ` · ${counts.noText} ${t("stat_no_text_sub")}` : ""}`;
  const cards = [
    ["total", t("stat_total"), counts.total, totalSub],
    ["high", t("stat_high"), counts.high, t("stat_click_filter")],
    ["medium", t("stat_medium"), counts.medium, t("stat_click_filter")],
    ["low", t("stat_low"), counts.low, t("stat_click_filter")],
  ];

  els.statCards.innerHTML = cards.map(([key, label, value, sub]) => {
    const active = key === "total" ? state.statFilter == null : state.statFilter === key;
    return `
      <button class="stat-card${active ? " active" : ""}" type="button" data-filter-card="${key}" aria-pressed="${active ? "true" : "false"}">
        <span class="stat-value">${escapeHtml(value)}</span>
        <span class="stat-label">${escapeHtml(label)}</span>
        <span class="stat-sub">${escapeHtml(sub)}</span>
      </button>
    `;
  }).join("");
}

// Detailed Riigikogu stage (raw enum, as the old site showed it) with a
// fallback to the coarse proceedingStatus mapping for rows without one.
function statusText(row) {
  if (row.active_stage) return row.active_stage;
  if (!row.status) return t("status_unknown");
  return t(`status_${row.status}`);
}

function renderStatusOptions() {
  if (!els.status) return;
  const stages = Array.from(new Set(state.rows.map((row) => row.active_stage).filter(Boolean)))
    .sort((left, right) => left.localeCompare(right, "et"));
  els.status.innerHTML = [["all", t("status_all")], ...stages.map((stage) => [stage, stage])]
    .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
}

function noTextReason(row) {
  const status = row?.text_status;
  if (!NO_TEXT_STATUSES.has(status)) return t("no_text");
  const formats = row?.text_formats ? ` (${row.text_formats})` : "";
  return `${t(`text_status_${status}`)}${formats}`;
}

function renderFindingCell(row) {
  if (!hasDocument(row)) {
    return `<span class="muted no-text" title="${escapeHtml(noTextReason(row))}">${escapeHtml(t("state_no_text"))}</span>`;
  }

  if (!hasAnalysis(row)) {
    return `<span class="muted not-analyzed">${escapeHtml(t("not_analyzed"))}</span>`;
  }

  if (rowFindingTotal(row) === 0) {
    return `<span class="zero-findings">${escapeHtml(t("zero_findings"))}</span>`;
  }

  const chips = [
    ["high", asNumber(row.high_count)],
    ["med", asNumber(row.medium_count)],
    ["low", asNumber(row.low_count)],
  ].filter(([, count]) => count > 0);

  return `<span class="finding-chips">${chips.map(([level, count]) => `<span class="chip ${level}">${escapeHtml(count)}</span>`).join("")}</span>`;
}

function renderRows(rows) {
  els.tbody.innerHTML = rows.map((row) => {
    const href = withLang(`/bill/${row.bill_id ?? ""}`);
    const movedAt = activityDate(row);
    const changedAt = movedAt ? formatDay(movedAt) : formatDateTime(row.doc_fetched_at || row.last_seen_at);
    const recheck = needsRecheck(row)
      ? `<span class="muted" title="${escapeHtml(t("recheck_note"))}"> · ${escapeHtml(t("state_recheck"))}</span>`
      : "";
    return `
      <tr data-href="${escapeHtml(href)}" data-status="${escapeHtml(row.active_stage || row.status || "unknown")}" tabindex="0">
        <td><a href="${escapeHtml(href)}">${escapeHtml(row.bill_number || row.bill_id || "")}</a></td>
        <td>${escapeHtml(row.title || "")}</td>
        <td>${escapeHtml(statusText(row))}</td>
        <td>${escapeHtml(changedAt)}${recheck}</td>
        <td>${renderFindingCell(row)}</td>
      </tr>
    `;
  }).join("");
}

function renderPagination(totalPages) {
  if (!els.pagination) return;
  els.pagination.hidden = totalPages <= 1;
  if (totalPages <= 1) {
    els.pagination.innerHTML = "";
    return;
  }

  els.pagination.innerHTML = Array.from({ length: totalPages }, (_, index) => {
    const page = index + 1;
    const active = page === state.page;
    return `<button type="button" data-page="${page}" class="${active ? "active" : ""}" aria-current="${active ? "page" : "false"}">${page}</button>`;
  }).join("");
}

function renderTable() {
  if (!els.tbody || !els.table || !els.empty) return;

  const rows = filteredRows();
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  if (state.page > totalPages) state.page = totalPages;
  if (state.page < 1) state.page = 1;

  const start = (state.page - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);

  const empty = rows.length === 0;
  els.table.hidden = empty;
  els.empty.hidden = !empty;
  if (empty) {
    els.empty.textContent = `0 ${t("stat_total")}`;
    els.tbody.innerHTML = "";
  } else {
    renderRows(pageRows);
  }

  renderPagination(totalPages);
}

function init(rows = []) {
  state = {
    rows: Array.isArray(rows) ? rows.slice() : [],
    statFilter: null,
    search: "",
    status: "all",
    page: 1,
    searchTimer: null,
  };

  collectElements();
  mountShell(els.shellHeader, renderHeader);
  mountShell(els.shellFooter, renderFooter);
  setupStaticText();
  renderStatusOptions();

  if (els.search) els.search.value = "";
  if (els.status) els.status.value = "all";

  bindEvents();
  renderStats();
  renderTable();
}

async function autoInit() {
  ({ renderHeader, renderFooter } = await import("./shell.js"));
  const rows = await fetchBillIndex();
  init(rows);
}

const isBrowser = typeof window !== "undefined" && typeof document !== "undefined";

if (isBrowser) {
  window.LawlabIndex = { init };
}

if (isBrowser && !window.__LAWLAB_TEST__) {
  let autoStarted = false;
  const startAutoInit = () => {
    if (autoStarted) return;
    autoStarted = true;
    autoInit();
  };

  if (document.readyState === "complete") {
    startAutoInit();
  } else {
    document.addEventListener("DOMContentLoaded", startAutoInit, { once: true });
    window.addEventListener("load", startAutoInit, { once: true });
  }
}

export { init };
