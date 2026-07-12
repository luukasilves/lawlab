// Live-page smoke runner: loads a URL in headless Chrome via CDP, waits for
// network-driven rendering, prints console messages + final DOM to stdout.
// Usage: node scripts/page_smoke.mjs <url> [waitMs]
// (dump-dom can't see post-load async renders; this can.)

import { spawn } from "node:child_process";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const url = process.argv[2];
const waitMs = Number(process.argv[3] || 8000);
const port = 9222 + Math.floor(Math.random() * 500);

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
  "--no-first-run", "--user-data-dir=/tmp/lawlab-smoke-" + port, "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  let target;
  for (let i = 0; i < 40; i++) {
    await sleep(250);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
      if (res.ok) { target = await res.json(); break; }
    } catch {}
  }
  if (!target) throw new Error("chrome CDP not reachable");

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let id = 0;
  const pending = new Map();
  const consoleLines = [];
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
    if (m.method === "Runtime.consoleAPICalled") {
      consoleLines.push(`[console.${m.params.type}] ` + m.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
    }
    if (m.method === "Runtime.exceptionThrown") {
      consoleLines.push("[exception] " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    }
  };
  const send = (method, params = {}) =>
    new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

  await send("Runtime.enable");
  await send("Page.enable");
  await sleep(waitMs);

  const html = await send("Runtime.evaluate", { expression: "document.documentElement.outerHTML", returnByValue: true });
  console.log("===CONSOLE===");
  for (const l of consoleLines) console.log(l);
  console.log("===DOM===");
  console.log(html.result.value);
  ws.close();
} finally {
  chrome.kill();
}
