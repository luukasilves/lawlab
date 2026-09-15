const STRINGS = {
  stat_total: "Eelnõusid kokku",
  stat_analyzed_sub: "analüüsitud",
  stat_no_text_sub: "ilma tekstita",
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
  status_unknown: "Uuenduste seisu ei õnnestunud laadida",
  state_no_text: "Tekst puudub",
  state_recheck: "kontroll ootel",
  fresh_stale: "Andmed võivad olla aegunud — viimane õnnestunud uuendus on vanem kui 48 tundi.",
  no_text: "Eelnõu teksti ei õnnestunud kätte saada",
  text_status_unsupported_format: "Eelnõu on avaldatud ainult vormingus, mida ei õnnestu lugeda",
  text_status_image_only_pdf: "Eelnõu on avaldatud ainult pildipõhise (skaneeritud) PDF-ina, millest teksti ei saa lugeda",
  text_status_empty_text: "Eelnõu failist ei õnnestunud teksti lugeda",
  text_status_download_failed: "Eelnõu faili allalaadimine Riigikogu serverist ebaõnnestus; proovime järgmisel kontrollil uuesti",
  text_status_convert_failed: "Eelnõu .doc-faili teisendamine ebaõnnestus; proovime järgmisel kontrollil uuesti",
  text_status_no_files: "Riigikogu ei ole eelnõu teksti veel avaldanud",
  not_analyzed: "Veel analüüsimata",
  not_analyzed_note: "Eelnõu tekst on olemas, aga analüüs ei ole veel valminud. Analüüs käivitub järgmise automaatse kontrolliga.",
  recheck_note: "Eelnõu on Riigikogus edasi liikunud pärast viimast tekstikontrolli; uuesti kontrollimine on ootel.",
  status_checked: "Viimane kontroll",
  status_bills_checked: "eelnõu kontrollitud",
  status_new: "uut",
  status_changed: "muutunud",
  status_analysed: "Viimane analüüs",
  status_analysed_n: "uut analüüsi",
  status_pending_n: "ootel",
  status_failed_ingest: "Viimane automaatne kontroll ebaõnnestus",
  status_failed_analyze: "Viimane analüüsikäik ebaõnnestus",
  status_suspect: "kontroll ei tagastanud ühtegi eelnõu",
  zero_findings: "Probleeme ei leitud",
};

export function t(key) {
  return STRINGS[key] || key;
}

export function getLang() {
  return "et";
}

// Mirrors the real helper: prefix a canonical path for the language.
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

export function applyStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
}

export { STRINGS };
