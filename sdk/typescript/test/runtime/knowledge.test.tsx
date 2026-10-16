// Knowledge: detecting `this.knowledge` use, rejecting the old field, and searching from a tool.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import Busca from "../agent/busca.js";
import ClinicaNorte from "../agent/clinica-norte.js";
import { declaredOnTheInstance } from "../../src/runtime/environment.js";
import { mount, optionsFor } from "../../src/runtime/connect.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";
const CALL = "CA_1";
const FILE = fileURLToPath(new URL("../agent/clinica-norte.tsx", import.meta.url));
const SOURCE = readFileSync(FILE, "utf8");
const BUSCA_FILE = fileURLToPath(new URL("../agent/busca.tsx", import.meta.url));
const BUSCA_SOURCE = readFileSync(BUSCA_FILE, "utf8");

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

/** Let pending socket work settle. */
async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

/** Wait up to a second for commands of `type` to arrive. */
async function answered(type: string): Promise<Record<string, unknown>[]> {
  for (let turn = 0; turn < 200 && commands(type).length === 0; turn++) await new Promise((resolve) => setTimeout(resolve, 5));
  return commands(type);
}

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

// `usesKnowledge` is parsed from the source so the gateway can refuse a world with no base at registration.
it("says it searches knowledge when the source reaches this.knowledge, and not otherwise", () => {
  expect(optionsFor(Busca, [], new Busca(), BUSCA_FILE, BUSCA_SOURCE).usesKnowledge).toBe(true);
  expect(optionsFor(ClinicaNorte, [], new ClinicaNorte(), FILE, SOURCE).usesKnowledge).toBeUndefined();
  // Without a source, the class body is parsed.
  expect(optionsFor(Busca, [], new Busca()).usesKnowledge).toBe(true);
  expect(optionsFor(ClinicaNorte, [], new ClinicaNorte(), FILE, `class X { doc = "this.knowledge is not a call"; }`).usesKnowledge).toBeUndefined();
});

it("runs a tool's search through the gateway, for this call, and hands the chunks back", async () => {
  mount(Busca, { pc, slug: SLUG, source: BUSCA_SOURCE, file: BUSCA_FILE });
  await pc.connect();
  await settled();
  gateway.finds([
    { path: "clinica.md", heading: "Horarios", text: "De nueve a ocho." },
    { path: "clinica.md", heading: "Dirección", text: "Calle Mayor 12." },
    { path: "tarifas.md", heading: "Revisión", text: "Cuarenta euros." },
  ]);
  gateway.emit(SLUG, CALL, "call.started", { channel: "phone", direction: "inbound", from: "+34 600 000 001", to: "+34 910 000 000", caller: null, started_at: Date.now() / 1000 });
  await settled();
  gateway.emit(SLUG, CALL, "tool.call", { call_id: "t1", name: "lookUp", arguments: { words: "horarios" } });
  const [result] = await answered("tool.result");
  expect(gateway.searched).toEqual([{ call: CALL, query: "horarios", k: 2 }]);
  expect(result?.["output"]).toBe("De nueve a ocho.\nCalle Mayor 12.");
});

it("refuses a search from an instance nobody is serving through a gateway", async () => {
  await expect(new Busca().knowledge.search("horarios")).rejects.toThrow("this.call is only there while a call is being served");
});

/** Old-style class that carried its knowledge file as a field. */
class DeMemoria extends ClinicaNorte {
  constructor() {
    super();
    // Assigned at runtime, as a class compiled against an older package would.
    Object.defineProperty(this, "knowledge", { value: "./knowledge/clinica.md", enumerable: true });
  }
}

it("refuses a knowledge file carried on the instance, where it would shadow this.knowledge", () => {
  expect(() => optionsFor(DeMemoria, [], new DeMemoria(), FILE, SOURCE)).toThrow(declaredOnTheInstance("knowledge"));
  expect(declaredOnTheInstance("knowledge")).toContain("static knowledge = …");
});
