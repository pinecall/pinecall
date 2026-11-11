// The app's page on this machine: its built folder, a route of its own read as the page, and what it asks before a ticket.

import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import type { Server } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, expect, it } from "vitest";

import { servePage } from "../../src/serve/paged.js";

let server: Server;
let at: string;

beforeEach(async () => {
  const folder = mkdtempSync(join(tmpdir(), "page-"));
  mkdirSync(join(folder, "assets"));
  writeFileSync(join(folder, "index.html"), "<!doctype html><title>Brightside</title>");
  writeFileSync(join(folder, "assets", "app.js"), "console.log(1)");
  server = await servePage({ folder, agent: "front-desk", door: { url: "http://127.0.0.1:1", apiKey: "pk_test" }, port: 0 });
  at = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(() => {
  server.close();
});

it("serves the page, its assets by their type, and a route of the page's own as the page", async () => {
  expect(await (await fetch(`${at}/`)).text()).toContain("<title>Brightside</title>");
  const asset = await fetch(`${at}/assets/app.js`);
  expect([asset.headers.get("content-type"), await asset.text()]).toEqual(["text/javascript", "console.log(1)"]);
  expect(await (await fetch(`${at}/visits/3`)).text()).toContain("<title>Brightside</title>");
});

it("answers 404 for a file that is not there, and never one outside its folder", async () => {
  expect((await fetch(`${at}/missing.png`)).status).toBe(404);
  expect((await fetch(`${at}/..%2F..%2Fetc%2Fpasswd.txt`)).status).toBe(404);
});

it("tells the page its agent, and asks for no captcha on this machine", async () => {
  expect(await (await fetch(`${at}/pinecall/config`)).json()).toEqual({ agent: "front-desk", turnstile: null });
});

it("answers the page when the gateway cannot be reached, in words", async () => {
  const refused = await fetch(`${at}/pinecall/token`, { method: "POST", body: JSON.stringify({ scope: "chat" }) });
  expect(refused.status).toBe(502);
  expect(typeof ((await refused.json()) as { detail: unknown }).detail).toBe("string");
});
