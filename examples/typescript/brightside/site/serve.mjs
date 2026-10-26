// Brightside's site on this machine, to talk to Pip: the page, the route a site with the widget needs,
// the dot's door, and the clinic's own search.
//
//   node site/serve.mjs            then open http://localhost:5173
//
// POST /pinecall/token mints the visitor's ticket with the org's key, as the widget's README ("Your two
// endpoints") says a site's server does. The key is PINECALL_KEY, else the one `pinecall link` wrote to
// ../.env; it never reaches the page. POST /pinecall/ask is the dot's door (the widget's `ask`): what
// the visitor types in the walks' menu, decided by @pinecall/dot/server with OPENROUTER_API_KEY, and a
// walk's sentence with slots recorded in Pip's voice with the org's key. GET /api/times is the clinic's
// search, which the page draws in its table. Until a release carries the tutor, the page takes the widget and
// @pinecall/room and @pinecall/dot from this checkout (their built dist/), through an import map;
// DOT_FROM=npm takes them from the gateway and jsDelivr instead.
import { existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../../..");
const PORT = Number(process.env.PORT ?? 5173);
const GATEWAY = (process.env.PINECALL_URL ?? "https://cloud.pinecall.io").replace(/\/+$/, "");
const KEY = process.env.PINECALL_KEY ?? keyInDotEnv();
const LOCAL = process.env.DOT_FROM !== "npm";
const AGENT = "pip";
const OPENROUTER = process.env.OPENROUTER_API_KEY ?? inDotEnv("OPENROUTER_API_KEY");
// The world Pip is held in while you write it (`pinecall start`), whose walks the page plays (`walks="sandbox"`).
const WALKS_ENV = "sandbox";

/** What is served from the checkout, by the path the page asks for. */
const SERVED = {
  "/widget/": join(repo, "widget"),
  "/dev/room/": join(repo, "packages/room/dist"),
  "/dev/dot/": join(repo, "packages/dot/dist"),
};
const TYPES = { ".js": "text/javascript", ".map": "application/json", ".html": "text/html; charset=utf-8" };
// The widget's dot imports both packages from jsDelivr; here those addresses lead to the checkout.
const IMPORTS = {
  imports: {
    "https://cdn.jsdelivr.net/npm/@pinecall/room@0.11/+esm": "/dev/room/index.js",
    "https://cdn.jsdelivr.net/npm/@pinecall/dot@0.11/+esm": "/dev/dot/index.js",
    "@pinecall/room": "/dev/room/index.js",
    zod: "https://cdn.jsdelivr.net/npm/zod@4/+esm",
    "livekit-client": "https://cdn.jsdelivr.net/npm/livekit-client@2/+esm",
  },
};

function inDotEnv(name) {
  const file = resolve(here, "../.env");
  if (!existsSync(file)) return "";
  const line = readFileSync(file, "utf8").split("\n").find((one) => one.startsWith(`${name}=`));
  return line ? line.slice(name.length + 1).trim() : "";
}

function keyInDotEnv() {
  return inDotEnv("PINECALL_KEY");
}

// The clinic's open times for the next two weeks, as its own system would answer them.
const TIMES = [
  ["Tuesday, Oct 28", "9:00", "Dr. Patel", "Cleaning"],
  ["Tuesday, Oct 28", "18:30", "Dr. Okafor", "Aligners consult"],
  ["Wednesday, Oct 29", "11:15", "Dr. Lin", "Implant consult"],
  ["Wednesday, Oct 29", "19:00", "Dr. Patel", "Whitening"],
  ["Thursday, Oct 30", "8:30", "Dr. Okafor", "Cleaning"],
  ["Thursday, Oct 30", "17:45", "Dr. Patel", "Cleaning"],
  ["Friday, Oct 31", "10:00", "Dr. Lin", "Implant consult"],
  ["Tuesday, Nov 4", "19:30", "Dr. Okafor", "Braces check"],
  ["Wednesday, Nov 5", "9:45", "Dr. Patel", "Whitening"],
  ["Thursday, Nov 6", "18:15", "Dr. Lin", "Cleaning"],
].map(([day, time, dentist, treatment]) => ({ day, time, dentist, treatment }));

/** The times that match the most words asked (a day, a dentist, a treatment); every time for none. A search takes a moment. */
async function times(res, q) {
  const words = q.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((word) => word.length > 2).map((word) => word.replace(/s$/, ""));
  const scored = TIMES.map((time) => {
    const said = `${time.day} ${time.dentist} ${time.treatment}`.toLowerCase();
    return { time, score: words.filter((word) => said.includes(word)).length };
  });
  const best = Math.max(0, ...scored.map((one) => one.score));
  const found = words.length === 0 ? TIMES : best === 0 ? [] : scored.filter((one) => one.score === best).map((one) => one.time);
  await new Promise((done) => setTimeout(done, 600));
  json(res, 200, found);
}

/** The dot's door, from the checkout's @pinecall/dot/server until a release carries it. */
const doorOf = (LOCAL ? import(join(repo, "packages/dot/dist/server/index.js")) : import("@pinecall/dot/server")).then((server) => server.answer);

async function ask(req, res) {
  let body = {};
  try {
    let text = "";
    for await (const chunk of req) text += chunk;
    body = JSON.parse(text || "{}");
  } catch {
    return json(res, 400, { detail: "the body is not JSON" });
  }
  if (!OPENROUTER) return json(res, 500, { detail: "no OPENROUTER_API_KEY: set it, or put it in ../.env" });
  const answer = await doorOf;
  const started = Date.now();
  const answered = await answer(body, { key: OPENROUTER, voicing: { key: KEY, agent: AGENT, gateway: GATEWAY, env: WALKS_ENV } });
  console.log(`ask ${Object.keys(body)[0]} → ${JSON.stringify(answered).slice(0, 160)} in ${Date.now() - started} ms`);
  json(res, 200, answered);
}

// The page reports what the face's ear hears once a second, to this server's log: where the ear
// stands (asleep, no voice, no track, listening), the level, how often the page was sent, and the
// agent's audio element and track. With ?debug the same shows in a label in the corner.
const DEBUG = `<script>
addEventListener("DOMContentLoaded", () => {
  const shown = new URLSearchParams(location.search).has("debug");
  const label = Object.assign(document.createElement("div"), { style: "position:fixed;left:12px;top:12px;z-index:2147483647;font:12px ui-monospace,monospace;background:#111;color:#fff;padding:6px 10px;border-radius:8px" });
  label.dataset.pinecallSkip = "";
  if (shown) document.body.append(label);
  let levels = [];
  setInterval(() => {
    const face = document.querySelector("[data-pc-ear]");
    if (face) levels.push(Number(face.dataset.pcLevel));
    if (shown) label.textContent = face ? "ear: " + face.dataset.pcEar + " · level " + face.dataset.pcLevel + " · page sent " + (face.dataset.pcSeen ?? 0) + "×" : "no face yet";
  }, 100);
  setInterval(() => {
    const face = document.querySelector("[data-pc-ear]");
    if (!face) return;
    const audio = [...document.querySelectorAll("audio")].map((one) => {
      const track = one.srcObject instanceof MediaStream ? one.srcObject.getAudioTracks()[0] : undefined;
      return { paused: one.paused, muted: one.muted, ready: one.readyState, track: track ? { state: track.readyState, muted: track.muted, enabled: track.enabled } : null };
    });
    const max = levels.length ? Math.max(...levels) : 0, mean = levels.length ? levels.reduce((a, b) => a + b, 0) / levels.length : 0;
    levels = [];
    fetch("/debug", { method: "POST", body: JSON.stringify({ ear: face.dataset.pcEar, level_max: +max.toFixed(2), level_mean: +mean.toFixed(2), seen: Number(face.dataset.pcSeen ?? 0), audio, ua: navigator.userAgent }) }).catch(() => {});
  }, 1000);
});
</script>`;

function page() {
  return readFileSync(join(here, "index.html"), "utf8")
    .replace("<!-- __DEV__ -->", (LOCAL ? `<script type="importmap">${JSON.stringify(IMPORTS)}</script>` : "") + DEBUG)
    .replace("__WIDGET__", LOCAL ? "/widget/pinecall-widget.js" : `${GATEWAY}/widget/pinecall-widget.js`)
    .replace("__GATEWAY__", GATEWAY);
}

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

async function token(req, res) {
  let asked = {};
  try {
    let text = "";
    for await (const chunk of req) text += chunk;
    asked = JSON.parse(text || "{}");
  } catch {
    return json(res, 400, { detail: "the body is not JSON" });
  }
  if (asked.agent !== AGENT) return json(res, 404, { detail: `this site serves ${AGENT} alone` });
  if (!KEY) return json(res, 500, { detail: "no PINECALL_KEY: run `pinecall link` in this folder, or set it" });
  const minted = await fetch(`${GATEWAY}/v1/tokens`, {
    method: "POST",
    headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ agent: AGENT, scope: asked.scope, ttl_s: 600, ...(asked.resume ? { resume: asked.resume } : {}) }),
  });
  res.writeHead(minted.status, { "content-type": "application/json" });
  res.end(await minted.text());
}

function file(res, path) {
  for (const [prefix, root] of Object.entries(SERVED)) {
    if (!path.startsWith(prefix)) continue;
    const found = normalize(join(root, path.slice(prefix.length)));
    if (!found.startsWith(root) || !existsSync(found) || !statSync(found).isFile()) break;
    res.writeHead(200, { "content-type": TYPES[extname(found)] ?? "application/octet-stream" });
    return res.end(readFileSync(found));
  }
  res.writeHead(404);
  res.end();
}

if (LOCAL) {
  for (const dist of [SERVED["/dev/room/"], SERVED["/dev/dot/"], join(SERVED["/dev/dot/"], "server")]) {
    if (!existsSync(join(dist, "index.js"))) {
      console.error(`${dist} is not built: run scripts/build in packages/room and packages/dot first`);
      process.exit(1);
    }
  }
}

createServer((req, res) => {
  const { pathname } = new URL(req.url ?? "/", "http://localhost");
  if (req.method === "POST" && pathname === "/debug") {
    let text = "";
    req.on("data", (chunk) => (text += chunk));
    req.on("end", () => {
      console.log(`debug ${new Date().toISOString().slice(11, 19)} ${text}`);
      res.writeHead(204);
      res.end();
    });
  } else if (req.method === "POST" && pathname === "/pinecall/token") {
    token(req, res).catch((failed) => json(res, 502, { detail: `the gateway could not be reached: ${failed.message}` }));
  } else if (req.method === "POST" && pathname === "/pinecall/ask") {
    ask(req, res).catch((failed) => json(res, 502, { detail: failed.message }));
  } else if (req.method === "GET" && pathname === "/api/times") {
    times(res, new URL(req.url ?? "/", "http://localhost").searchParams.get("q") ?? "");
  } else if (pathname === "/" || pathname === "/index.html") {
    res.writeHead(200, { "content-type": TYPES[".html"] });
    res.end(page());
  } else {
    file(res, pathname);
  }
}).listen(PORT, () => {
  console.log(`Brightside on http://localhost:${PORT}  (agent ${AGENT} at ${GATEWAY}, ${LOCAL ? "packages from this checkout" : "packages from npm"})`);
});
