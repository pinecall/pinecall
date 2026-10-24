// Brightside's site on this machine, to talk to Pip: the page, and the one route a site with the widget needs.
//
//   node site/serve.mjs            then open http://localhost:5173
//
// POST /pinecall/token mints the visitor's ticket with the org's key, as the widget's README ("Your two
// endpoints") says a site's server does. The key is PINECALL_KEY, else the one `pinecall link` wrote to
// ../.env; it never reaches the page. Until a release carries the tutor, the page takes the widget and
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

function keyInDotEnv() {
  const file = resolve(here, "../.env");
  if (!existsSync(file)) return "";
  const line = readFileSync(file, "utf8").split("\n").find((one) => one.startsWith("PINECALL_KEY="));
  return line ? line.slice("PINECALL_KEY=".length).trim() : "";
}

function page() {
  return readFileSync(join(here, "index.html"), "utf8")
    .replace("<!-- __DEV__ -->", LOCAL ? `<script type="importmap">${JSON.stringify(IMPORTS)}</script>` : "")
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
  for (const dist of [SERVED["/dev/room/"], SERVED["/dev/dot/"]]) {
    if (!existsSync(join(dist, "index.js"))) {
      console.error(`${dist} is not built: run scripts/build in packages/room and packages/dot first`);
      process.exit(1);
    }
  }
}

createServer((req, res) => {
  const { pathname } = new URL(req.url ?? "/", "http://localhost");
  if (req.method === "POST" && pathname === "/pinecall/token") {
    token(req, res).catch((failed) => json(res, 502, { detail: `the gateway could not be reached: ${failed.message}` }));
  } else if (pathname === "/" || pathname === "/index.html") {
    res.writeHead(200, { "content-type": TYPES[".html"] });
    res.end(page());
  } else {
    file(res, pathname);
  }
}).listen(PORT, () => {
  console.log(`Brightside on http://localhost:${PORT}  (agent ${AGENT} at ${GATEWAY}, ${LOCAL ? "packages from this checkout" : "packages from npm"})`);
});
