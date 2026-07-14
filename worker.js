// Router for pretty URLs on Workers Static Assets. html_handling is "none"
// (the default canonicalizer 307-redirects *.html fetches, breaking rewrites),
// so every page route is mapped here explicitly; other paths are raw assets.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const page = (name) =>
      env.ASSETS.fetch(new Request(new URL(`/${name}.html`, url), request));

    // English pages live under an /en prefix (same HTML; the page JS reads the
    // language from the URL path). The browser URL is preserved because these
    // serve an asset rather than redirect.
    const p = url.pathname;
    if (p === "/" || p === "/index.html" || p === "/en" || p === "/en/") return page("index");
    if (p.startsWith("/bill/") || p.startsWith("/en/bill/")) return page("bill");
    if (p === "/metoodika" || p === "/metoodika/" || p === "/en/metoodika" || p === "/en/metoodika/") return page("metoodika");
    return env.ASSETS.fetch(request);
  },
};
