// `serve prompt`: the prompt a state produces, offline, opened in the state its pairs name.

import { EventEmitter } from "node:events";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough, Writable } from "node:stream";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { main } from "../../src/serve/index.js";
import { stateOf } from "../../src/serve/prompt.js";

const AGENT = fileURLToPath(new URL("./clinic/agents/clinica-norte/agent.tsx", import.meta.url));

async function printed(...argv: string[]): Promise<{ code: number; out: string; err: string }> {
  let out = "";
  let err = "";
  const into = (keep: (text: string) => void): Writable =>
    new Writable({ write: (chunk: Buffer, _encoding, done) => { keep(chunk.toString()); done(); } });
  const io = {
    out: into((text) => (out += text)),
    err: into((text) => (err += text)),
    env: {},
    input: new PassThrough(),
    signals: new EventEmitter(),
  };
  const code = await main(["prompt", ...argv], io);
  return { code, out, err };
}

describe("serve prompt", () => {
  it("prints the view of the state its pairs name, and the machine when asked", async () => {
    const opened = await printed("--file", AGENT, "--slug", "clinica-norte", "--state", 'patient={"name":"Ana"}', "--state", "slots=[{},{}]", "--show-machine");
    expect(opened.code).toBe(0);
    expect(opened.out).toContain("Ofrece 2 horas y pregunta cuál prefiere.");
    expect(opened.out).toContain("── tools ──");
  });

  it("prints the class's own state when no pair is named, and no machine unless asked", async () => {
    const plain = await printed("--file", AGENT, "--slug", "clinica-norte");
    expect(plain.out).toContain("Saluda y pide nombre y teléfono.");
    expect(plain.out).not.toContain("── tools ──");
  });

  it("refuses a pair that is no JSON, by its field, exit 2", async () => {
    const refused = await printed("--file", AGENT, "--slug", "clinica-norte", "--state", "patient={nope");
    expect(refused.code).toBe(2);
    expect(refused.err).toContain("--state patient: its value is not JSON");
    expect(() => stateOf(["=1"])).toThrow(/a field, =, and its value as JSON/);
  });

  it("refuses a prompt that names no file, in a sentence, exit 2", async () => {
    const said = await printed();
    expect(said.code).toBe(2);
    expect(said.err).toContain("takes the agent's --file");
  });

  it("refuses an environment field on the instance, in the sentence that names the static one, exit 2", async () => {
    const file = join(mkdtempSync(join(tmpdir(), "serve-")), "agent.ts");
    const agent = fileURLToPath(new URL("../../src/agent/agent.ts", import.meta.url));
    writeFileSync(file, `import { Agent } from ${JSON.stringify(agent)};\n/** Una. */\nexport default class Una extends Agent {\n  language = "es";\n}\n`);
    const refused = await printed("--file", file, "--slug", "una");
    expect(refused.code).toBe(2);
    expect(refused.err).toBe("`language` is the class's, not a call's state: declare it as static language = …\n");
  });
});
