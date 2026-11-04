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
    expect(ran.err).toBe("pinecall: limits has no option --version\n  → pinecall limits --help shows its flags\n");
  });

  it("a verb nobody wrote, or a flag nobody declared, is 2, said in the CLI's words with the help that lists them", async () => {
    const verb = await run(["deploi"]);
    expect(verb.code).toBe(2);
    expect(verb.err).toBe('pinecall: no verb "deploi" (did you mean deploy?)\n  → pinecall --help lists them\n');
    const flag = await run(["limits", "--everything"]);
    expect(flag.code).toBe(2);
    expect(flag.err).toBe("pinecall: limits has no option --everything\n  → pinecall limits --help shows its flags\n");
  });

  it("a word too many, an argument or a flag missing: the verb typed, what it takes, and its help", async () => {
    expect((await run(["lexicon", "list"])).err).toBe('pinecall: lexicon takes no argument, and "list" was typed\n  → pinecall lexicon --help says what it takes\n');
    expect((await run(["sessions", "show", "call_1"])).err).toBe('pinecall: sessions takes 1 argument, and "show call_1" was typed\n  → pinecall sessions --help says what it takes\n');
    // A word that is one of the verb's flags, typed without its dashes: the flag is the next step.
    expect((await run(["agent", "clear", "language"])).err).toBe('pinecall: agent clear takes no argument, and "language" was typed\n  → pinecall agent clear --language\n');
    expect((await run(["memory"])).err).toBe("pinecall: memory needs a <contact>\n  → pinecall memory --help says what it takes\n");
    expect((await run(["lexicon", "add", "DKV"])).err).toBe("pinecall: lexicon add needs --say <spoken>\n  → pinecall lexicon add --help shows its flags\n");
    expect((await run(["sessions", "--limit"])).err).toBe("pinecall: --limit <n> takes a value, and none was typed\n  → pinecall sessions --help shows its flags\n");
  });

  it("an input a schema refuses is one sentence and 2, not a dump of the schema", async () => {
    const ran = await run(["monitors", "add", "x", "--metric", "latency", "--above", "1"]);
    expect(ran.code).toBe(2);
    expect(ran.err.trim().split("\n")).toHaveLength(1);
    expect(ran.err).toMatch(/^pinecall: --metric names one of/);
  });

  it("every refusal of the gateway is 2, in its own words with no status in front: the command could not run, and measured nothing", async () => {
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
      expect([ran.code, ran.err], String(status)).toEqual([2, `pinecall: ${detail}\n`]);
    }
  });

  it("a body with no sentence in it names the status; an agent of the project the gateway never met is said to have never been held", async () => {
    server.use(http.get(`${GATEWAY}/v1/limits`, () => new HttpResponse("<html>bad gateway</html>", { status: 502 })));
    expect((await run(["limits"])).err).toBe("pinecall: the gateway answered 502: <html>bad gateway</html>\n");
    refuse("get", "/v1/agents/:slug/settings", 404, "no agent front-desk in this org: `pinecall agent list` names the ones there are");
    expect((await run(["agent"])).err).toBe("pinecall: front-desk is not on Pinecall yet, nothing has held it\n  → pinecall start holds it from this terminal, pinecall deploy runs it on Pinecall\n");
    refuse("get", "/v1/agents/:slug/settings", 404, "no agent sales in this org: `pinecall agent list` names the ones there are");
    expect((await run(["agent", "--agent", "sales"])).err).toBe("pinecall: no agent sales in this org\n  → pinecall agent list names the ones there are\n");
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
