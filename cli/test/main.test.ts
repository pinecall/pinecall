/** The entry: every failure one sentence on stderr and one exit code — 0 did it, 1 what was measured did not hold, 2 it could not run, 130 stopped. */

import { readFileSync } from "node:fs";
import { Writable } from "node:stream";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import { main } from "../src/main.js";
import { StreamIO } from "../src/kit/io.js";
import { answer, GATEWAY, refuse, server } from "./support/gateway.js";
import { folder } from "./support/project.js";
import { run } from "./support/run.js";

const VERSION = (JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as { version: string }).version;

describe("the exit codes", () => {
  it("nothing typed prints the verbs by what they are for, on one screen, and exits 0", async () => {
    const ran = await run([]);
    expect(ran.code).toBe(0);
    expect(ran.out.split("\n").length).toBeLessThanOrEqual(20);
    expect(ran.out).toContain("start · console · chat");
    expect(ran.out).toContain("pinecall --help");
  });

  it("the reader of a pipe that closed is nobody to print for: no stack, exit 0", async () => {
    const closed = new Writable({
      write(_chunk, _encoding, done) {
        done(Object.assign(new Error("write EPIPE"), { code: "EPIPE" }));
      },
    });
    const err: string[] = [];
    const stderr = new Writable({
      write(chunk: Buffer, _encoding, done) {
        err.push(chunk.toString());
        done();
      },
    });
    expect(await main(["--version"], new StreamIO(closed, stderr), { PINECALL_HOME: folder() }, folder())).toBe(0);
    expect(err.join("")).toBe("");
  });

  it("--help and --version are answers, exit 0", async () => {
    expect((await run(["--help"])).code).toBe(0);
    const version = await run(["--version"]);
    expect([version.code, version.out]).toEqual([0, `${VERSION}\n`]);
    expect((await run(["-v"])).out).toBe(`${VERSION}\n`);
    expect((await run(["--prod", "--version"])).out).toBe(`${VERSION}\n`);
  });

  it("the version flag reaches no verb: after one, `--version` is its own", async () => {
    const ran = await run(["limits", "--version"]);
    expect(ran.code).toBe(2);
    expect(ran.out).toBe("");
    expect(ran.err).toContain("unknown option '--version'");
  });

  it("a verb nobody wrote, or a flag nobody declared, is 2", async () => {
    expect((await run(["deploi"])).code).toBe(2);
    const flag = await run(["limits", "--everything"]);
    expect(flag.code).toBe(2);
    expect(flag.err).toContain("unknown option '--everything'");
  });

  it("an input a schema refuses is one sentence and 2, not a dump of the schema", async () => {
    const ran = await run(["monitors", "add", "x", "--metric", "latency", "--above", "1"]);
    expect(ran.code).toBe(2);
    expect(ran.err.trim().split("\n")).toHaveLength(1);
    expect(ran.err).toMatch(/^pinecall: --metric names one of/);
  });

  it("every refusal of the gateway is 2, in its own words: the command could not run, and measured nothing", async () => {
    for (const [status, detail] of [
      [400, "no vendor named 'nosuchvendor' is installed here"],
      [401, "the key is not one this gateway knows"],
      [403, "this key may not read the org's limits"],
      [404, "no such org"],
      [409, "a run is going"],
      [422, "window: Input should be a valid integer"],
      [429, "the org has used 4 of its 4 concurrent calls in the sandbox"],
      [503, "xai has no key: the org brought none and the box holds none"],
    ] as const) {
      refuse("get", "/v1/limits", status, detail);
      const ran = await run(["limits"]);
      expect([ran.code, ran.err], String(status)).toEqual([2, `pinecall: the gateway answered ${status}: ${detail}\n`]);
    }
  });

  it("a network that is down is 2: the command could not run", async () => {
    server.use(http.get(`${GATEWAY}/v1/limits`, () => HttpResponse.error()));
    const ran = await run(["limits"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toMatch(/^pinecall: .+\n$/);
  });

  it("--prod and --json go anywhere on the line", async () => {
    const sent = answer("get", "/v1/monitors", { monitors: [] });
    for (const argv of [["--prod", "monitors"], ["monitors", "--prod"], ["monitors", "list", "--prod", "--json"]]) expect((await run(argv)).code).toBe(0);
    expect(sent.map((one) => one.env)).toEqual(["production", "production", "production"]);
  });
});
