# UI parity gaps vs old lawlab.ilves.ai (captured 2026-07-13, DOM dumps)

Task: duplicate the old site's elements (user request), keep our "better"
additions. Old texts are authoritative for labels. Work through ALL items,
then re-run web/test harnesses + scripts/page_smoke.mjs against local +
deployed, then redeploy.

## Shell (web/js/shell.js, i18n.js)
1. Tagline (header, under wordmark): ET+EN both -> "AI analüüsib Riigikogu
   seaduseelnõusid" / EN "AI analyses Estonian draft legislation" (old used
   the ET line; keep EN translation).
2. Nav: the methodology link is labelled "About" in BOTH languages (old site
   brand quirk) -> i18n key nav_method = "About"/"About".
3. Footer: add "Andmeallikas: Riigikogu" with link to https://www.riigikogu.ee
   (old footer element), keep GitHub + Andmed/API links.

## Index (web/js/index.js, i18n.js)
4. Stat cards -> EXACTLY four: "Eelnõusid kokku" (subtext "N analüüsitud"),
   "Kõrge risk", "Keskmine risk", "Madal risk"; the three risk cards get
   subtext "Kliki filtreerimiseks" / EN "Click to filter"; clicking risk card
   filters rows with that severity count > 0; total card clears.
   (Replace current stat_analyzed/stat_findings cards; keep counts logic.)
5. Status column shows DETAILED stage from api_data.activeDraftStatus (raw
   enum like MENETLUSSE_VOETUD, as on old site; fallback: proceedingStatus
   mapped Menetluses/Menetletud). Dropdown "Kõik staatused" lists distinct
   stages present in data. NOTE: bill_index view lacks api_data -> simplest:
   add active_stage to the bill_index VIEW (b.api_data->>'activeDraftStatus')
   via SQL (idempotent create or replace; run against pooler + schema.sql).
6. Search placeholder: "Otsi pealkirja järgi..." / EN "Search by title...".

## Detail (web/js/bill.js, i18n.js)
7. Metadata cards: add 4th card "Prompt versioon" -> value
   `${prompt_version} — ${interpretive pass name_et/en}` (e.g. "ic-v1 —
   Tõlgenduslik analüüs").
8. Under "Analüüsi tulemused" header add summary line (old format):
   "Analüüsitud: {text_length locale-formatted} märki · Dokumendid: eelnõu ·
   Prompt: {prompt_version}" (ET) / EN equivalent.
9. Severity badges show ET/EN words: Kõrge/Keskmine/Madal (EN High/Medium/
   Low), not raw HIGH/MEDIUM/LOW.
10. History header: "Analüüside ajalugu (N)" with count.

## About page (web/js/metoodika.js)
11. Lead sections restructured to mirror old site (headers verbatim, ours
    where marked):
    a. "Andmeallikad" — sub-blocks: "Riigikogu API" (link api.riigikogu.ee),
       "Dokumendid" (DOCX eelnõu; NB: seletuskirja veel ei analüüsita),
       "Andmete uuendamine" (daily cron 05:00 UTC, freshness from
       pipeline_runs).
    b. "AI mudel" — model id from methodology.json engine.model, sampling
       params (N/k/temperature), and "Teksti piirang" sub-block stating: NO
       truncation (vana versioon piiras 30 000 märgiga; uus analüüsib kogu
       teksti).
    c. "Süsteemi promptid" — per-pass <details> "Näita {version} prompti"
       (exists; relabel buttons to match old pattern).
    d. Keep our extra sections after these: Analüüsi käik (pipeline),
       Kontrollid, Kategooriad ja HÕNTE, Piirangud, Andmed/API (#andmed),
       gold-set note.
12. Page <title> and h1: "About".

## Verification
- Update harness fixtures/assertions where labels changed (test_index
  stat-card assertions; test_bill severity-label assertion if any).
- All 4 harnesses ALL-PASS; page_smoke local index+bill+metoodika; deploy;
  page_smoke against workers.dev; commit.
