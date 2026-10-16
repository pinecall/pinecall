// The org's feed through observe: its own door, the types asked for, and a word each time it opens.

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, expect, it } from "vitest";
import { observe } from "../../src/client/observe.js";

const CHANGED = { seq: 0, ts: 1, call: null, agent: "", type: "run.changed", ephemeral: true, data: { run: "run_1", agent: "ana", finished: true } };

let server: Server;
let base: string;
const asked: string[] = [];

beforeEach(async () => {
  asked.length = 0;
  server = createServer((request, response) => {
    asked.push(request.url ?? "");
    response.writeHead(200, { "content-type": "text/event-stream" });
    response.write(`event: run.changed\ndata: ${JSON.stringify(CHANGED)}\n\n`);
  });
  await new Promise<void>((bound) => server.listen(0, "127.0.0.1", bound));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(async () => {
  server.closeAllConnections();
  await new Promise<void>((closed) => server.close(() => closed()));
});

it("follows the feed at /v1/events, asks the gateway for the types it wants, and says when a stream opens", async () => {
  const stop = new AbortController();
  let opened = 0;
  for await (const { entry } of observe({ feed: true }, { url: base, apiKey: "pk_test", types: ["run.changed", "release.changed"], onOpen: () => (opened += 1), signal: stop.signal })) {
    expect(entry.type).toBe("run.changed");
    stop.abort();
  }
  expect(asked).toEqual(["/v1/events?types=run.changed%2Crelease.changed"]);
  expect(opened).toBe(1);
});
