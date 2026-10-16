/** The entry: every failure one sentence on stderr and one exit code — 0 did it, 1 refused or failed, 2 the arguments, 130 stopped. */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { answer, refuse } from "./support/gateway.js";
import { run } from "./support/run.js";

const VERSION = (JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as { version: string }).version;

describe("the exit codes", () => {
  it("nothing typed prints the whole CLI and exits 2", async () => {
    const ran = await run([]);
    expect(ran.code).toBe(2);
    expect(ran.out).toContain("Usage: pinecall [options] [command]");
  });

  it("--help and --version are answers, exit 0", async () => {
    expect((await run(["--help"])).code).toBe(0);
    const version = await run(["--version"]);
    expect([version.code, version.out]).toEqual([0, `${VERSION}\n`]);
    expect((await run(["-v"])).out).toBe(`${VERSION}\n`);
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

  it("the gateway's refusal is 1, in its own words", async () => {
    refuse("get", "/v1/limits", 403, "this key may not read the org's limits");
    const ran = await run(["limits"]);
    expect(ran.code).toBe(1);
    expect(ran.err).toBe("pinecall: the gateway answered 403: this key may not read the org's limits\n");
  });

  it("--prod and --json go anywhere on the line", async () => {
    const sent = answer("get", "/v1/monitors", { monitors: [] });
    for (const argv of [["--prod", "monitors"], ["monitors", "--prod"], ["monitors", "list", "--prod", "--json"]]) expect((await run(argv)).code).toBe(0);
    expect(sent.map((one) => one.env)).toEqual(["production", "production", "production"]);
  });
});
