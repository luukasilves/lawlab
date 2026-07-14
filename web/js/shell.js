import { applyStatic, getLang, stripLang, t, withLang } from './i18n.js';

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

function isStale(iso) {
  if (!iso) {
    return false;
  }
  const date = new Date(iso);
  return !Number.isNaN(date.getTime()) && Date.now() - date.getTime() > 48 * 60 * 60 * 1000;
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
  document.documentElement.lang = getLang();
  const mount = active instanceof Element ? active : document.querySelector('#app-header');
  const activeName = active instanceof Element ? (active.dataset.active || '') : active;
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

// `freshnessISO` is either an ISO timestamp rendered into #app-footer, or a
// mount element (index.js shows freshness in its own line instead).
export function renderFooter(freshnessISO = null) {
  document.documentElement.lang = getLang();
  const mount = freshnessISO instanceof Element ? freshnessISO : document.querySelector('#app-footer');
  const iso = freshnessISO instanceof Element ? (window.LAWLAB_FRESHNESS_ISO || null) : freshnessISO;
  if (!mount) {
    return;
  }

  const formatted = formatDateTime(iso);
  const stale = isStale(iso);

  mount.innerHTML = `
    <footer class="site-footer">
      <div class="container footer-inner">
        <div class="footer-links">
          <span class="footer-source">${t('footer_source')}: <a href="https://www.riigikogu.ee">Riigikogu</a></span>
          <a href="https://github.com/luukasilves/lawlab">GitHub</a>
          <a href="${withLang('/metoodika')}#andmed" data-i18n="api_docs"></a>
        </div>
        <div class="last-updated" data-last-updated>
          ${formatted ? `<span>${t('fresh_updated')}: <time datetime="${iso}">${formatted}</time></span>` : ''}
        </div>
      </div>
      ${stale ? `<div class="container"><div class="banner-stale">${t('fresh_stale')}</div></div>` : ''}
    </footer>
  `;
  applyStatic(mount);
}

window.LawlabShell = { renderHeader, renderFooter };

if (!window.__LAWLAB_TEST__) {
  document.addEventListener('DOMContentLoaded', () => {
    renderHeader(document.body?.dataset.active);
    renderFooter(window.LAWLAB_FRESHNESS_ISO || null);
  });
}
