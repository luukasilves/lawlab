import { applyStatic, getLang, setLang, t } from './i18n.js';

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

function wireLangToggle(root) {
  const button = root.querySelector('[data-lang-toggle]');
  if (!button) {
    return;
  }
  button.addEventListener('click', () => {
    setLang(getLang() === 'en' ? 'et' : 'en');
    location.reload();
  });
}

export function renderHeader(active) {
  document.documentElement.lang = getLang();
  const mount = document.querySelector('#app-header');
  if (!mount) {
    return;
  }

  const billsActive = isActive('bills', active);
  const methodActive = isActive('method', active);
  const nextLang = getLang() === 'en' ? 'ET' : 'EN';

  mount.innerHTML = `
    <header class="site-header">
      <div class="container header-inner">
        <a class="brand" href="/" aria-label="Apsakaleidja">
          <span class="wordmark">Apsakaleidja</span>
          <span class="beta-chip" data-i18n="beta"></span>
        </a>
        <p class="tagline" data-i18n="tagline"></p>
        <nav class="site-nav" aria-label="Primary">
          <a href="/" data-i18n="nav_bills" class="${billsActive ? 'active' : ''}" ${billsActive ? 'aria-current="page"' : ''}></a>
          <a href="/metoodika" data-i18n="nav_method" class="${methodActive ? 'active' : ''}" ${methodActive ? 'aria-current="page"' : ''}></a>
          <button class="lang-toggle" type="button" data-lang-toggle aria-label="Switch language">${nextLang}</button>
        </nav>
      </div>
    </header>
  `;
  applyStatic(mount);
  wireLangToggle(mount);
}

export function renderFooter(freshnessISO = null) {
  document.documentElement.lang = getLang();
  const mount = document.querySelector('#app-footer');
  if (!mount) {
    return;
  }

  const formatted = formatDateTime(freshnessISO);
  const stale = isStale(freshnessISO);

  mount.innerHTML = `
    <footer class="site-footer">
      <div class="container footer-inner">
        <div class="footer-links">
          <a href="https://github.com/luukasilves/lawlab">GitHub</a>
          <a href="/metoodika#andmed" data-i18n="api_docs"></a>
        </div>
        <div class="last-updated" data-last-updated>
          ${formatted ? `<span>${t('fresh_updated')}: <time datetime="${freshnessISO}">${formatted}</time></span>` : ''}
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
