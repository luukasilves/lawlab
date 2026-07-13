const STRINGS = {
  stat_total: "Eelnõusid kokku",
  stat_analyzed_sub: "analüüsitud",
  stat_high: "Kõrge risk",
  stat_medium: "Keskmine risk",
  stat_low: "Madal risk",
  stat_click_filter: "Kliki filtreerimiseks",
  search_ph: "Otsi pealkirja järgi...",
  th_number: "Number",
  th_title: "Pealkiri",
  th_status: "Staatus",
  th_changed: "Muudetud",
  th_findings: "Leiud",
  status_all: "Kõik staatused",
  status_IN_PROCESS: "Menetluses",
  status_PROCESSED: "Menetletud",
  status_unknown: "Teadmata",
  fresh_updated: "Andmed uuendatud",
  fresh_stale: "Andmed on aegunud",
  no_text: "Tekst puudub",
  not_analyzed: "Analüüsimata",
  zero_findings: "Leide ei ole",
};

export function t(key) {
  return STRINGS[key] || key;
}

export function applyStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
}

export { STRINGS };
