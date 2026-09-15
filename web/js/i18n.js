export const dict = {
  et: {
    tagline: 'AI analüüsib Riigikogu seaduseelnõusid',
    nav_bills: 'Eelnõud',
    nav_method: 'About',
    beta: 'BETA',
    footer_source: 'Andmeallikas',
    stat_total: 'Eelnõusid kokku',
    stat_analyzed_sub: 'analüüsitud',
    stat_high: 'Kõrge risk',
    stat_medium: 'Keskmine risk',
    stat_low: 'Madal risk',
    stat_click_filter: 'Kliki filtreerimiseks',
    search_ph: 'Otsi pealkirja järgi...',
    th_number: 'Number',
    th_title: 'Pealkiri',
    th_status: 'Staatus',
    th_changed: 'Muudetud',
    th_findings: 'Leiud',
    status_all: 'Kõik staatused',
    status_IN_PROCESS: 'Menetluses',
    status_PROCESSED: 'Menetletud',
    status_unknown: 'Uuenduste seisu ei õnnestunud laadida',
    state_no_text: 'Tekst puudub',
    state_recheck: 'kontroll ootel',
    stat_no_text_sub: 'ilma tekstita',
    fresh_stale: 'Andmed võivad olla aegunud — viimane õnnestunud uuendus on vanem kui 48 tundi.',
    no_text: 'Eelnõu teksti ei õnnestunud kätte saada',
    text_status_unsupported_format: 'Eelnõu on avaldatud ainult vormingus, mida ei õnnestu lugeda',
    text_status_image_only_pdf: 'Eelnõu on avaldatud ainult pildipõhise (skaneeritud) PDF-ina, millest teksti ei saa lugeda',
    text_status_empty_text: 'Eelnõu failist ei õnnestunud teksti lugeda',
    text_status_download_failed: 'Eelnõu faili allalaadimine Riigikogu serverist ebaõnnestus; proovime järgmisel kontrollil uuesti',
    text_status_convert_failed: 'Eelnõu .doc-faili teisendamine ebaõnnestus; proovime järgmisel kontrollil uuesti',
    text_status_no_files: 'Riigikogu ei ole eelnõu teksti veel avaldanud',
    not_analyzed: 'Veel analüüsimata',
    not_analyzed_note: 'Eelnõu tekst on olemas, aga analüüs ei ole veel valminud. Analüüs käivitub järgmise automaatse kontrolliga.',
    recheck_note: 'Eelnõu on Riigikogus edasi liikunud pärast viimast tekstikontrolli; uuesti kontrollimine on ootel.',
    status_checked: 'Viimane kontroll',
    status_bills_checked: 'eelnõu kontrollitud',
    status_new: 'uut',
    status_changed: 'muutunud',
    status_analysed: 'Viimane analüüs',
    status_analysed_n: 'uut analüüsi',
    status_pending_n: 'ootel',
    status_failed_ingest: 'Viimane automaatne kontroll ebaõnnestus',
    status_failed_analyze: 'Viimane analüüsikäik ebaõnnestus',
    status_suspect: 'kontroll ei tagastanud ühtegi eelnõu',
    zero_findings: 'Probleeme ei leitud',
    back: 'Tagasi nimekirja',
    view_riigikogu: 'Vaata Riigikogu veebis',
    meta_type: 'Liik',
    meta_committee: 'Juhtivkomisjon',
    meta_updated: 'Viimati uuendatud',
    meta_prompt: 'Prompt versioon',
    severity_HIGH: 'Kõrge',
    severity_MEDIUM: 'Keskmine',
    severity_LOW: 'Madal',
    summary_analyzed: 'Analüüsitud',
    summary_chars: 'märki',
    summary_documents: 'Dokumendid',
    summary_prompt: 'Prompt',
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
    tagline: 'AI analyses Estonian draft legislation',
    nav_bills: 'Bills',
    nav_method: 'About',
    beta: 'BETA',
    footer_source: 'Data source',
    stat_total: 'Total bills',
    stat_analyzed_sub: 'analysed',
    stat_high: 'High risk',
    stat_medium: 'Medium risk',
    stat_low: 'Low risk',
    stat_click_filter: 'Click to filter',
    search_ph: 'Search by title...',
    th_number: 'Number',
    th_title: 'Title',
    th_status: 'Status',
    th_changed: 'Updated',
    th_findings: 'Findings',
    status_all: 'All statuses',
    status_IN_PROCESS: 'In proceedings',
    status_PROCESSED: 'Concluded',
    status_unknown: 'Could not load update status',
    state_no_text: 'No text',
    state_recheck: 're-check pending',
    stat_no_text_sub: 'without text',
    fresh_stale: 'Data may be stale — the last successful update is older than 48 hours.',
    no_text: 'The bill text could not be retrieved',
    text_status_unsupported_format: 'The bill is published only in a format that cannot be read',
    text_status_image_only_pdf: 'The bill is published only as an image-only (scanned) PDF from which text cannot be read',
    text_status_empty_text: 'No text could be read from the bill file',
    text_status_download_failed: 'Downloading the bill file from the Riigikogu server failed; we will retry on the next check',
    text_status_convert_failed: 'Converting the bill’s .doc file failed; we will retry on the next check',
    text_status_no_files: 'The Riigikogu has not published the bill text yet',
    not_analyzed: 'Not yet analysed',
    not_analyzed_note: 'The bill text is available but has not been analysed yet. Analysis runs with the next automatic check.',
    recheck_note: 'The bill has moved in the Riigikogu since the text was last checked; a re-check is pending.',
    status_checked: 'Last check',
    status_bills_checked: 'bills checked',
    status_new: 'new',
    status_changed: 'changed',
    status_analysed: 'Last analysis',
    status_analysed_n: 'new analyses',
    status_pending_n: 'pending',
    status_failed_ingest: 'The last automatic check failed',
    status_failed_analyze: 'The last analysis run failed',
    status_suspect: 'the check returned no bills',
    zero_findings: 'No problems found',
    back: 'Back to the list',
    view_riigikogu: 'View at Riigikogu',
    meta_type: 'Type',
    meta_committee: 'Lead committee',
    meta_updated: 'Last updated',
    meta_prompt: 'Prompt version',
    severity_HIGH: 'High',
    severity_MEDIUM: 'Medium',
    severity_LOW: 'Low',
    summary_analyzed: 'Analysed',
    summary_chars: 'characters',
    summary_documents: 'Documents',
    summary_prompt: 'Prompt',
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

// The URL is the single source of truth for language: English pages live under
// an `/en` path prefix (`/en`, `/en/bill/:id`, `/en/metoodika`) so they are
// linkable and shareable. Everything else is Estonian (the default, unprefixed).
export function langFromPath(pathname) {
  const path = pathname != null
    ? pathname
    : (typeof window !== 'undefined' ? window.location?.pathname ?? '' : '');
  return /^\/en(\/|$)/.test(path) ? 'en' : DEFAULT_LANG;
}

// Strip the `/en` prefix to get the canonical (Estonian) path.
export function stripLang(pathname) {
  const path = pathname != null
    ? pathname
    : (typeof window !== 'undefined' ? window.location?.pathname ?? '/' : '/');
  const stripped = path.replace(/^\/en(?=\/|$)/, '');
  return stripped || '/';
}

// Prefix a canonical (Estonian) path for the given language. `/` becomes `/en`.
export function withLang(canonicalPath, lang = getLang()) {
  let path = canonicalPath || '/';
  if (!path.startsWith('/')) {
    path = `/${path}`;
  }
  if (normalizeLang(lang) !== 'en') {
    return path;
  }
  return path === '/' ? '/en' : `/en${path}`;
}

// Explicit override, set only by setLang() — used by test harnesses and any
// programmatic caller. In the live site nothing sets it, so getLang() stays
// purely path-driven and pages render deterministically from their URL.
let override = null;

export function getLang() {
  if (override) {
    return override;
  }
  try {
    return langFromPath();
  } catch (error) {
    // Non-browser context; fall back to any stored preference.
  }
  try {
    return normalizeLang(window.localStorage.getItem(STORAGE_KEY));
  } catch (error) {
    return DEFAULT_LANG;
  }
}

export function setLang(lang) {
  override = normalizeLang(lang);
  try {
    window.localStorage.setItem(STORAGE_KEY, override);
  } catch (error) {
    // Ignore storage failures; the current render can still use the normalized value.
  }
  return override;
}

export function t(key) {
  return dict[getLang()][key] || key;
}

export function applyStatic(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.getAttribute('data-i18n'));
  });
}
