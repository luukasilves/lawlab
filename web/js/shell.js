import { fetchPipelineRuns } from './api.js';
import { applyStatic, getLang, stripLang, t, withLang } from './i18n.js';

const STALE_AFTER_MS = 48 * 60 * 60 * 1000;

function isActive(name, active) {
  if (active) {
    return active === name;
  }
  if (name === 'bills') {
    return location.pathname === '/' || location.pathname.endsWith('/index.html') || location.pathname.startsWith('/bill');
  }
  if (name === 'method') {
    return location.pathname.startsWith('/metoodika');
  }
  return false;
}

function formatDateTime(iso) {
  if (!iso) {
    return '';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(getLang() === 'en' ? 'en-GB' : 'et-EE', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function asNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function runTime(run) {
  const time = Date.parse(run?.started_at || run?.finished_at || '');
  return Number.isFinite(time) ? time : 0;
}

function displayTime(run) {
  return run?.finished_at || run?.started_at || '';
}

function newestRun(runs, kind, predicate = () => true) {
  return runs
    .filter((run) => run?.kind === kind && predicate(run))
    .sort((left, right) => runTime(right) - runTime(left))[0] || null;
}

function isGoodIngest(run) {
  const seen = Number(run?.stats?.seen);
  const total = run?.stats?.bills_total;
  return run?.ok === true
    && seen > 0
    && (!total || seen >= 0.5 * Number(total));
}

function problemError(run) {
  const error = run?.stats?.error;
  if (error) {
    return String(error);
  }
  return run?.ok === true ? t('status_suspect') : '';
}

export function summarizeRuns(runs, now = Date.now()) {
  const rows = Array.isArray(runs) ? runs : [];
  const latestIngest = newestRun(rows, 'ingest');
  const latestAnalyze = newestRun(rows, 'analyze');
  const lastGoodIngest = newestRun(rows, 'ingest', isGoodIngest);
  const lastGoodAnalyze = newestRun(rows, 'analyze', (run) => run?.ok === true);
  const problems = [];

  if (latestIngest && !isGoodIngest(latestIngest)) {
    problems.push({ kind: 'ingest', run: latestIngest, error: problemError(latestIngest) });
  }
  if (latestAnalyze && latestAnalyze.ok !== true) {
    problems.push({ kind: 'analyze', run: latestAnalyze, error: problemError(latestAnalyze) });
  }

  const problem = problems.sort((left, right) => runTime(right.run) - runTime(left.run))[0] || null;
  const goodIngestTime = Date.parse(displayTime(lastGoodIngest));
  const stale = !Number.isFinite(goodIngestTime) || now - goodIngestTime > STALE_AFTER_MS;
  const state = rows.length === 0
    ? 'unknown'
    : problem
      ? 'failed'
      : stale
        ? 'stale'
        : 'ok';

  return {
    lastGoodIngest,
    lastGoodAnalyze,
    problem,
    stale,
    state
  };
}

// The toggle navigates to the same page in the other language rather than
// reloading, so the language is always reflected in (and driven by) the URL.
function otherLangHref() {
  const other = getLang() === 'en' ? 'et' : 'en';
  const canonical = stripLang(location.pathname);
  return `${withLang(canonical, other)}${location.search}${location.hash}`;
}

function wireLangToggle(root) {
  const button = root.querySelector('[data-lang-toggle]');
  if (!button) {
    return;
  }
  button.addEventListener('click', () => {
    location.assign(otherLangHref());
  });
}

// hreflang alternates + canonical make the ET/EN pages linkable and correctly
// indexed. Rebuilt on each render; tagged so re-renders don't stack duplicates.
function injectAlternates() {
  if (typeof document === 'undefined' || !document.head) {
    return;
  }
  const canonical = stripLang(location.pathname);
  document.head.querySelectorAll('link[data-lawlab-alt]').forEach((node) => node.remove());
  const add = (rel, hreflang, href) => {
    const link = document.createElement('link');
    link.rel = rel;
    if (hreflang) {
      link.hreflang = hreflang;
    }
    link.href = href;
    link.setAttribute('data-lawlab-alt', '');
    document.head.appendChild(link);
  };
  add('canonical', null, withLang(canonical, getLang()));
  add('alternate', 'et', withLang(canonical, 'et'));
  add('alternate', 'en', withLang(canonical, 'en'));
  add('alternate', 'x-default', withLang(canonical, 'et'));
}

// `active` is either a nav name ('bills'/'method') rendered into #app-header,
// or a mount element (index.js hands us its own #app-shell-header div).
export function renderHeader(active) {
  if (typeof document === 'undefined') {
    return;
  }
  document.documentElement.lang = getLang();
  const directMount = typeof Element !== 'undefined' && active instanceof Element;
  const mount = directMount ? active : document.querySelector('#app-header');
  const activeName = directMount ? (active.dataset.active || '') : active;
  if (!mount) {
    return;
  }

  const billsActive = isActive('bills', activeName);
  const methodActive = isActive('method', activeName);
  const nextLang = getLang() === 'en' ? 'ET' : 'EN';
  const billsHref = withLang('/');
  const methodHref = withLang('/metoodika');

  mount.innerHTML = `
    <header class="site-header">
      <div class="container header-inner">
        <a class="brand" href="${billsHref}" aria-label="Apsakaleidja">
          <span class="wordmark">Apsakaleidja</span>
          <span class="beta-chip" data-i18n="beta"></span>
        </a>
        <p class="tagline" data-i18n="tagline"></p>
        <nav class="site-nav" aria-label="Primary">
          <a href="${billsHref}" data-i18n="nav_bills" class="${billsActive ? 'active' : ''}" ${billsActive ? 'aria-current="page"' : ''}></a>
          <a href="${methodHref}" data-i18n="nav_method" class="${methodActive ? 'active' : ''}" ${methodActive ? 'aria-current="page"' : ''}></a>
          <button class="lang-toggle" type="button" data-lang-toggle aria-label="Switch language">${nextLang}</button>
        </nav>
      </div>
    </header>
  `;
  applyStatic(mount);
  wireLangToggle(mount);
  injectAlternates();
}

function formatCount(value) {
  const number = asNumber(value);
  return number == null ? null : new Intl.NumberFormat(getLang() === 'en' ? 'en-GB' : 'et-EE').format(number);
}

function firstNumber(stats, keys) {
  for (const key of keys) {
    const number = asNumber(stats?.[key]);
    if (number != null) {
      return number;
    }
  }
  return null;
}

function renderRunLine(label, run, countParts) {
  if (!run) {
    return `${escapeHtml(label)}: -`;
  }
  const iso = displayTime(run);
  const formatted = formatDateTime(iso) || '-';
  const parts = [
    `<time datetime="${escapeHtml(iso)}">${escapeHtml(formatted)}</time>`,
    ...countParts.filter(Boolean).map(escapeHtml)
  ];
  return `${escapeHtml(label)}: ${parts.join(' · ')}`;
}

function renderWarning(summary) {
  if (summary.state === 'failed' && summary.problem) {
    const key = summary.problem.kind === 'analyze' ? 'status_failed_analyze' : 'status_failed_ingest';
    const time = formatDateTime(displayTime(summary.problem.run)) || '-';
    const details = [t(key), time, summary.problem.error].filter(Boolean).map(escapeHtml);
    return `<div class="banner-stale">${details.join(' · ')}</div>`;
  }
  if (summary.state === 'stale') {
    return `<div class="banner-stale">${escapeHtml(t('fresh_stale'))}</div>`;
  }
  if (summary.state === 'unknown') {
    return `<div class="banner-stale">${escapeHtml(t('status_unknown'))}</div>`;
  }
  return '';
}

export function renderPipelineStatus(summary, mount) {
  const target = mount?.matches?.('[data-pipeline-status]')
    ? mount
    : mount?.querySelector?.('[data-pipeline-status]');
  if (!target) {
    return;
  }

  const ingestStats = summary.lastGoodIngest?.stats || {};
  const ingestCounts = [
    formatCount(ingestStats.seen) ? `${formatCount(ingestStats.seen)} ${t('status_bills_checked')}` : null,
    formatCount(ingestStats.new) ? `${formatCount(ingestStats.new)} ${t('status_new')}` : null,
    formatCount(ingestStats.changed) ? `${formatCount(ingestStats.changed)} ${t('status_changed')}` : null
  ];
  const analyzeStats = summary.lastGoodAnalyze?.stats || {};
  const analysed = firstNumber(analyzeStats, ['analysed', 'analyzed', 'new', 'completed']);
  const pending = firstNumber(analyzeStats, ['pending']);
  const analyzeCounts = [
    analysed != null ? `${formatCount(analysed)} ${t('status_analysed_n')}` : null,
    pending > 0 ? `${formatCount(pending)} ${t('status_pending_n')}` : null
  ];

  target.dataset.state = summary.state;
  target.innerHTML = `
    <span>${renderRunLine(t('status_checked'), summary.lastGoodIngest, ingestCounts)}</span>
    <span>${renderRunLine(t('status_analysed'), summary.lastGoodAnalyze, analyzeCounts)}</span>
    ${renderWarning(summary)}
  `;
}

// `mount` can be the footer mount, null/undefined (meaning #app-footer), or
// absent in non-browser imports.
export async function renderFooter(mount = undefined) {
  if (typeof document === 'undefined') {
    return summarizeRuns(null);
  }
  document.documentElement.lang = getLang();
  const directMount = typeof Element !== 'undefined' && mount instanceof Element;
  const root = directMount ? mount : document.querySelector('#app-footer');
  if (!root) {
    return summarizeRuns(null);
  }

  root.innerHTML = `
    <footer class="site-footer">
      <div class="container footer-inner">
        <div class="footer-links">
          <span class="footer-source">${t('footer_source')}: <a href="https://www.riigikogu.ee">Riigikogu</a></span>
          <a href="https://github.com/luukasilves/lawlab">GitHub</a>
          <a href="${withLang('/metoodika')}#andmed" data-i18n="api_docs"></a>
        </div>
        <div class="last-updated" data-last-updated data-pipeline-status data-state="loading">
          <span>${escapeHtml(t('status_checked'))}: -</span>
          <span>${escapeHtml(t('status_analysed'))}: -</span>
        </div>
      </div>
    </footer>
  `;
  applyStatic(root);

  let summary;
  try {
    summary = summarizeRuns(await fetchPipelineRuns());
  } catch (error) {
    summary = summarizeRuns(null);
  }
  renderPipelineStatus(summary, root);
  return summary;
}

if (typeof window !== 'undefined') {
  window.LawlabShell = { renderHeader, renderFooter, renderPipelineStatus, summarizeRuns };
}

if (typeof window !== 'undefined' && typeof document !== 'undefined' && !window.__LAWLAB_TEST__) {
  document.addEventListener('DOMContentLoaded', () => {
    renderHeader(document.body?.dataset.active);
    renderFooter();
  });
}
