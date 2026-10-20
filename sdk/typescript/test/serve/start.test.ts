// `serve start`: what the CLI starts an agent with — the wire on stdout, the view alone, a drained leave.

import { EventEmitter } from "node:events";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough, Writable } from "node:stream";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { FakeGateway } from "../../src/client/testing/index.js";
import { main } from "../../src/serve/index.js";
import type { Io } from "../../src/serve/io.js";
import { drainLine } from "../../src/serve/leaving.js";
import { ONLY_THE_VIEW } from "../../src/serve/start.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";
const AGENT = fileURLToPath(new URL("./clinic/agents/clinica-norte/agent.tsx", import.meta.url));

let gateway: FakeGateway | null = null;

afterEach(async () => {
  await gateway?.close();
  gateway = null;
});

/** An Io whose output is kept as text, whose stdin and signals the test drives. */
function anIo(env: Record<string, string>): Io & { written: () => string[]; said: () => string } {
  const out: string[] = [];
  const err: string[] = [];
  const into = (kept: string[]): Writable =>
    new Writable({ write: (chunk: Buffer, _encoding, done) => { kept.push(chunk.toString()); done(); } });
  return {
    out: into(out),
    err: into(err),
    env,
    input: new PassThrough(),
    signals: new EventEmitter(),
    written: () => out.join("").split("\n").filter((line) => line !== ""),
    said: () => err.join(""),
  };
}

// A deadline in time, never a count of tries: on a loaded runner a 5 ms sleep takes far longer.
const WITHIN_MS = 10_000;

// A test waits on until() twice at most; vitest's default 5 s would cut it before its own deadline.
vi.setConfig({ testTimeout: 2 * WITHIN_MS });

async function until(found: () => boolean): Promise<void> {
  const deadline = Date.now() + WITHIN_MS;
  while (!found() && Date.now() < deadline) await new Promise((wake) => setTimeout(wake, 5));
  expect(found()).toBe(true);
}

async function serving(...flags: string[]): Promise<{ io: ReturnType<typeof anIo>; running: Promise<number>; held: FakeGateway }> {
  const held = await FakeGateway.start({ apiKey: KEY, holdsDrain: flags.includes("--holds-drain") });
  gateway = held;
  const io = anIo({ PINECALL_URL: held.url, PINECALL_KEY: KEY });
  const running = main(["start", "--file", AGENT, "--slug", SLUG, ...flags.filter((flag) => flag !== "--holds-drain")], io);
  await until(() => held.commandsOf("agent.configure").length > 0);
  return { io, running, held };
}

describe("the wire on stdout", () => {
  it("is agent.registered first, the entry as the gateway wrote it, with the app it was given", async () => {
    const { io, running } = await serving("--events");
    const [first] = io.written();
    expect(JSON.parse(first!)).toEqual({ type: "agent.registered", agent: SLUG, call: null, data: expect.objectContaining({ app: "app_1" }) });
    (io.input as PassThrough).end();
    expect(await running).toBe(0);
  });

  it("registers under the slug it was given, and a console's process takes no unclaimed call", async () => {
    const { io, running, held } = await serving("--console");
    expect(held.commandsOf("agent.register")[0]).toMatchObject({ agent: SLUG, data: { takes_unclaimed: false } });
    (io.input as PassThrough).end();
    await running;
  });
});

describe("the console's verbs", () => {
  it("are refused, all but view.render, which the class answers", async () => {
    const { io, running, held } = await serving();
    held.emit(SLUG, null, "dev.request", { id: "dev_1", verb: "goldens.roster", data: {} });
    held.emit(SLUG, null, "dev.request", { id: "dev_2", verb: "view.render", data: { contact: "+34600", call: "CA_1" } });
    await until(() => held.commandsOf("dev.answer").length === 2);
    const answers = held.commandsOf("dev.answer").map((answer) => answer.data);
    expect(answers).toContainEqual({ id: "dev_1", refused: { status: 404, detail: ONLY_THE_VIEW } });
    expect(answers).toContainEqual({ id: "dev_2", refused: { status: 404, detail: expect.stringContaining("declares no view") } });
    (io.input as PassThrough).end();
    await running;
  });
});

describe("leaving", () => {
  it("drains every agent when its stdin ends, before the socket closes", async () => {
    const { io, running, held } = await serving();
    (io.input as PassThrough).end();
    expect(await running).toBe(0);
    expect(held.commandsOf("agent.drain")).toHaveLength(1);
    expect(io.said()).toContain("draining · no live calls");
  });

  it("drains on SIGTERM, and leaves at once on a second signal while the drain waits", async () => {
    const { io, running, held } = await serving("--holds-drain");
    io.signals.emit("SIGTERM");
    await until(() => held.commandsOf("agent.drain").length === 1);
    io.signals.emit("SIGINT");
    expect(await running).toBe(0);
    expect(io.said()).not.toContain("draining");
  });

  it("says in one line where the calls went and what became of the tools", () => {
    expect(drainLine({ handed: 0, parked: 0, tools: 0, finished: 0 })).toBe("draining · no live calls");
    expect(drainLine({ handed: 1, parked: 2, tools: 2, finished: 1 })).toBe(
      "draining · 1 live call handed over · 2 live calls kept for the next process · 1 tool finished · 1 tool cut",
    );
  });
});

describe("what cannot be served", () => {
  it("is a door it was not given, said in a sentence, exit 2", async () => {
    const io = anIo({});
    expect(await main(["start", "--file", AGENT, "--slug", SLUG], io)).toBe(2);
    expect(io.said()).toContain("PINECALL_URL and PINECALL_KEY");
  });

  it("is a class whose own slug is not the one it is served as", async () => {
    const folder = mkdtempSync(join(tmpdir(), "serve-"));
    const file = join(folder, "agent.ts");
    const agent = fileURLToPath(new URL("../../src/agent/agent.js", import.meta.url)).replace(/\.js$/, ".ts");
    writeFileSync(file, `import { Agent } from ${JSON.stringify(agent)};\n/** Una. */\nexport default class Otra extends Agent {\n  static slug = "otra";\n}\n`);
    const io = anIo({ PINECALL_URL: "http://127.0.0.1:1", PINECALL_KEY: KEY });
    expect(await main(["start", "--file", file, "--slug", "una"], io)).toBe(2);
    expect(io.said()).toContain("says its slug is otra, and it is served as una");
  });
});

describe("a registration the gateway refuses", () => {
  it("is one sentence on err and exit 2, never a stack", async () => {
    const held = await FakeGateway.start({ apiKey: KEY, taken: [SLUG] });
    gateway = held;
    const io = anIo({ PINECALL_URL: held.url, PINECALL_KEY: KEY });

    const code = await main(["start", "--file", AGENT, "--slug", SLUG], io);

    expect(code).toBe(2);
    expect(io.said()).toContain(`${SLUG} answers at a door somebody else has`);
    expect(io.said()).not.toContain("    at ");
  });
});
