export const dict = {
  et: {
    tagline: 'Eesti eelnõude automaatne veakontroll',
    nav_bills: 'Eelnõud',
    nav_method: 'Metoodika',
    beta: 'BETA',
    stat_total: 'Eelnõusid',
    stat_analyzed: 'Analüüsitud',
    stat_high: 'Kõrge risk',
    stat_findings: 'Leide kokku',
    search_ph: 'Otsi numbri või pealkirja järgi…',
    th_number: 'Number',
    th_title: 'Pealkiri',
    th_status: 'Staatus',
    th_changed: 'Muudetud',
    th_findings: 'Leiud',
    status_all: 'Kõik staatused',
    status_IN_PROCESS: 'Menetluses',
    status_PROCESSED: 'Menetletud',
    status_unknown: 'Teadmata',
    fresh_updated: 'Andmed uuendatud',
    fresh_stale: 'Andmed võivad olla aegunud — viimane õnnestunud uuendus on vanem kui 48 tundi.',
    no_text: 'Eelnõu teksti ei õnnestunud kätte saada (vorming ei ole toetatud).',
    not_analyzed: 'Veel analüüsimata',
    zero_findings: 'Probleeme ei leitud',
    back: 'Tagasi nimekirja',
    view_riigikogu: 'Vaata Riigikogu veebis',
    meta_type: 'Liik',
    meta_committee: 'Juhtivkomisjon',
    meta_updated: 'Viimati uuendatud',
    results: 'Analüüsi tulemused',
    pipeline: 'Analüüsi käik',
    samples: 'Näidised',
    sample_reused: 'taaskasutatud',
    refuted_section: 'Skeptiku poolt ümber lükatud',
    skeptic_upheld: 'skeptik kinnitas',
    skeptic_refuted: 'ümber lükatud',
    agreement: 'Kooskõla',
    source_rule: 'reegel',
    source_model: 'mudel',
    confirm: 'Kinnita',
    dismiss: 'Lükka tagasi',
    feedback_thanks: 'Aitäh! Tagasiside salvestatud.',
    feedback_error: 'Salvestamine ebaõnnestus.',
    history: 'Analüüside ajalugu',
    cost: 'Kulu',
    duration: 'Kestus',
    tokens: 'Tokenid',
    raw_json: 'Toorandmed (JSON)',
    api_docs: 'Andmed / API'
  },
  en: {
    tagline: 'Automated error-checking for Estonian draft legislation',
    nav_bills: 'Bills',
    nav_method: 'Methodology',
    beta: 'BETA',
    stat_total: 'Bills',
    stat_analyzed: 'Analysed',
    stat_high: 'High risk',
    stat_findings: 'Total findings',
    search_ph: 'Search by number or title…',
    th_number: 'Number',
    th_title: 'Title',
    th_status: 'Status',
    th_changed: 'Updated',
    th_findings: 'Findings',
    status_all: 'All statuses',
    status_IN_PROCESS: 'In proceedings',
    status_PROCESSED: 'Concluded',
    status_unknown: 'Unknown',
    fresh_updated: 'Data updated',
    fresh_stale: 'Data may be stale — the last successful update is older than 48 hours.',
    no_text: 'The bill text could not be extracted (unsupported format).',
    not_analyzed: 'Not yet analysed',
    zero_findings: 'No problems found',
    back: 'Back to the list',
    view_riigikogu: 'View at Riigikogu',
    meta_type: 'Type',
    meta_committee: 'Lead committee',
    meta_updated: 'Last updated',
    results: 'Analysis results',
    pipeline: 'How this analysis was made',
    samples: 'Samples',
    sample_reused: 'reused',
    refuted_section: 'Refuted by the skeptic pass',
    skeptic_upheld: 'skeptic upheld',
    skeptic_refuted: 'refuted',
    agreement: 'Agreement',
    source_rule: 'rule',
    source_model: 'model',
    confirm: 'Confirm',
    dismiss: 'Dismiss',
    feedback_thanks: 'Thanks! Feedback recorded.',
    feedback_error: 'Saving failed.',
    history: 'Analysis history',
    cost: 'Cost',
    duration: 'Duration',
    tokens: 'Tokens',
    raw_json: 'Raw data (JSON)',
    api_docs: 'Data / API'
  }
};

const STORAGE_KEY = 'lawlab_lang';
const DEFAULT_LANG = 'et';

function normalizeLang(lang) {
  return lang === 'en' ? 'en' : DEFAULT_LANG;
}

export function getLang() {
  try {
    return normalizeLang(window.localStorage.getItem(STORAGE_KEY));
  } catch (error) {
    return DEFAULT_LANG;
  }
}

export function setLang(lang) {
  const nextLang = normalizeLang(lang);
  try {
    window.localStorage.setItem(STORAGE_KEY, nextLang);
  } catch (error) {
    // Ignore storage failures; the current render can still use the normalized value.
  }
  return nextLang;
}

export function t(key) {
  return dict[getLang()][key] || key;
}

export function applyStatic(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.getAttribute('data-i18n'));
  });
}
