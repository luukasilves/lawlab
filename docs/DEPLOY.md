# Deploy & routing

The viewer is static files in `web/` (vanilla ES modules, no build step). It
is deployed **two ways to the same account**, because each solves a different
problem:

| Host | URL | Why it exists |
|------|-----|---------------|
| **Cloudflare Workers** | `lawlab.luukas-ilves.workers.dev` | Primary/canonical. Programmatic router (`worker.js`), most flexible. |
| **Cloudflare Pages** | `lawlab-9rk.pages.dev` (project `lawlab`) | Only way to attach a custom domain (`lawlab.ilves.ai`) whose DNS stays at an **external** registrar — Workers custom domains require the zone to be on Cloudflare. |

Keep both current. Deploy commands:

```bash
npx wrangler deploy                                              # Workers
npx wrangler pages deploy web --project-name lawlab --branch main --commit-dirty=true   # Pages
```

## Routing model

Pretty URLs (`/bill/<uuid>`, `/metoodika`) and the `/en` language prefix
(below) are **not** files — each host maps them to the right HTML while
preserving the browser URL (no redirect, so the page JS can read the path).

- **Workers** — `worker.js` maps every route explicitly and falls through to
  `env.ASSETS` for real files. `wrangler.jsonc` sets `assets.html_handling:
  "none"` (the default canonicalizer 307-redirects `*.html`, which breaks
  rewrites) and `assets.run_worker_first: true`.
- **Pages** — `web/_redirects` (200-rewrites; a Pages-only feature). Rewrite
  destinations are **clean paths** (`/bill`, `/metoodika`), never `*.html`.

### Gotcha 1 — Workers: `run_worker_first` is required

Without it, Cloudflare's static-asset layer runs *before* the Worker and
returns 404 for any path with no matching asset (`/bill/<uuid>`, `/en/*`) —
the router never runs. Symptom: `/` and `/metoodika` work (matched early) but
`/bill/<uuid>` 404s. `run_worker_first: true` makes the router authoritative;
it still serves real assets via the `return env.ASSETS.fetch(request)`
fallback.

### Gotcha 2 — Pages: never rewrite to a `.html` target

Pages serves clean URLs natively (`/metoodika` → `metoodika.html`) and
308-redirects `*.html` → clean. A `_redirects` rule like
`/metoodika /metoodika.html 200` therefore loops (`/metoodika` → 308 →
`/metoodika`), and `/bill/* /bill.html 200` strips the UUID (`/bill/x` → 308 →
`/bill`). Fix: drop redundant rules (Pages serves `/metoodika` itself) and
point splats at the clean path: `/bill/* /bill 200`.

### Gotcha 3 — cached 404s look like broken routing

Cloudflare edge-caches responses (incl. 404s, `cache-control:
max-age=0, must-revalidate` still HITs). After fixing a route, a stale 404 can
persist. Confirm with `cf-cache-status` and bust with `?cb=$RANDOM` before
concluding a route is broken.

## Language routing (`/en`)

The URL is the single source of truth for language. Estonian is the default,
unprefixed; English lives under `/en`:

```
/                 /en                 (index)
/bill/<uuid>      /en/bill/<uuid>     (detail)
/metoodika        /en/metoodika       (about)
```

`web/js/i18n.js` owns it: `langFromPath()` reads the prefix, `withLang(path,
lang)` builds links, `stripLang(path)` recovers the canonical path. `getLang()`
derives language from the path (localStorage/`setLang` override is a
test-harness fallback only, so live pages render deterministically from their
URL). Every internal link is built through `withLang`; the language toggle
navigates to the same page in the other language; `shell.js` injects
`canonical` + `hreflang` alternates. Both routers map the `/en` prefix to the
same HTML.

## DNS: pointing `lawlab.ilves.ai` at the site

`ilves.ai` nameservers are at Spaceship; email is Google Workspace
(`MX → smtp.google.com`) — do not disturb it.

**Recommended — Pages + external DNS (no zone move, one record):**
1. Cloudflare → Workers & Pages → **`lawlab` Pages project** → Custom domains →
   Set up a domain → `lawlab.ilves.ai`. It detects external DNS and shows a
   CNAME target (`lawlab-9rk.pages.dev`); confirm (status → Pending). **Do this
   before step 2**, or Cloudflare serves a 522 until it's registered.
2. Spaceship → ilves.ai → Advanced DNS: **delete** the `lawlab` A record
   (`185.158.133.1`, the old Lovable site — deleting it is the cutover) and
   **add** CNAME `lawlab` → `lawlab-9rk.pages.dev`. A and CNAME can't coexist on
   one host, so the delete must come first.
3. Wait ~5 min; Cloudflare validates and issues the cert (status → Active).

**Alternative — move the zone to Cloudflare (keeps the Worker):** Add site
`ilves.ai` in Cloudflare, verify the record scan captured MX + the
google-verification TXT, then replace Spaceship's nameservers
(`launch1/launch2.spaceship.net`) with Cloudflare's two. Attach
`lawlab.ilves.ai` to the `lawlab` Worker under Settings → Domains & Routes.
More power (Cloudflare analytics/caching) at the cost of the whole-zone move.
