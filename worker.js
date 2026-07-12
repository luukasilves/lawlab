// Router for pretty URLs on Workers Static Assets. html_handling is "none"
// (the default canonicalizer 307-redirects *.html fetches, breaking rewrites),
// so every page route is mapped here explicitly; other paths are raw assets.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const page = (name) =>
      env.ASSETS.fetch(new Request(new URL(`/${name}.html`, url), request));

    if (url.pathname === "/" || url.pathname === "/index.html") return page("index");
    if (url.pathname.startsWith("/bill/")) return page("bill");
    if (url.pathname === "/metoodika" || url.pathname === "/metoodika/") return page("metoodika");
    return env.ASSETS.fetch(request);
  },
};
