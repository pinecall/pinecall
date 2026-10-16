// The runtime bridge against a fake gateway: class behaviour to wire commands.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import ClinicaNorte from "../agent/clinica-norte.js";
import { mount, optionsFor, slugOf, type Mounted } from "../../src/runtime/connect.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";
const CALL = "CA_1";
const KNOWN = "+34 600 000 001";
// Source is passed so tool parameter types survive transpilation into the schema.
const FILE = fileURLToPath(new URL("../agent/clinica-norte.tsx", import.meta.url));
const SOURCE = readFileSync(FILE, "utf8");

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  // Tests assert on the wire; silence the client's default error printing.
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

async function connected(ctor: typeof ClinicaNorte = ClinicaNorte): Promise<void> {
  mounted = mount(ctor, { pc, source: SOURCE, file: FILE, slug: SLUG });
  await pc.connect();
  await settled();
}

function line(from: string): Record<string, unknown> {
  return { channel: "phone", direction: "inbound", from, to: "+34 910 000 000", caller: null, started_at: Date.now() / 1000 };
}

function started(from = KNOWN, over: Record<string, unknown> = {}): void {
  gateway.emit(SLUG, CALL, "call.started", { ...line(from), ...over });
}

function calls(name: string, args: Record<string, unknown>, id = `t${name}`): void {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: id, name, arguments: args });
}

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

it("registers the class under its name in kebab-case, with its four tools and no door", async () => {
  await connected();
  expect(slugOf(ClinicaNorte)).toBe(SLUG);
  const [register] = commands("agent.register");
  // The fixture sets `phone`/`whatsapp`/`web`, but routes come from the org, not the class.
  expect(register?.["routes"]).toEqual([]);
  const config = commands("agent.configure")[0]?.["config"] as { tools: { name: string }[]; prompt: unknown };
  expect(config.tools.map((tool) => tool.name)).toEqual([
    "findPatient",
    "freeSlots",
    "book",
    "transfer",
  ]);
  expect(config.prompt).toEqual([
    { name: "identity", region: "static" },
    { name: "knowledge", region: "static" },
    { name: "tools", region: "static" },
    { name: "view", region: "dynamic" },
  ]);
});

// The gateway fills the knowledge block; empty blocks are not sent.
it("sends every block that has text, in send order, and the visible tools when a call starts", async () => {
  await connected();
  started();
  await settled();
  expect(commands("prompt.set").map((data) => data["name"])).toEqual(["identity", "tools", "view"]);
  const [tools] = commands("tools.set");
  expect((tools?.["tools"] as { name: string }[]).map((tool) => tool.name)).toEqual([
    "freeSlots",
    "transfer",
  ]);
});

// onCall finds nobody at this number; the opening state names the patient, so the first render does.
it("opens a call in the state call.started carries, between onCall and the first render", async () => {
  await connected();
  const patient = { id: "p9", name: "Marta", phone: "+34 600 000 009" };
  started("+34 000 000 000", { state: { patient } });
  await settled();
  const sets = commands("state.set");
  expect(sets).toHaveLength(1);
  expect(sets[0]?.["state"]).toMatchObject({ patient });
  expect(commands("prompt.set").map((data) => data["name"])).toEqual(["identity", "tools", "view"]);
  const [tools] = commands("tools.set");
  expect((tools?.["tools"] as { name: string }[]).map((tool) => tool.name)).not.toContain("findPatient");
});

/** A view that does not read `slots`. */
class SoloDosCosas extends ClinicaNorte {
  override render() {
    return <p>{this.identified ? "identificado" : "sin identificar"} {this.done ? "cerrado" : "abierto"}</p>;
  }
}

it("sends state.set and no prompt.set when the tool wrote a field the view never reads", async () => {
  await connected(SoloDosCosas);
  started();
  await settled();
  const before = commands("prompt.set").length;
  calls("freeSlots", { day: "2026-03-02" });
  await settled();
  expect(commands("state.set").at(-1)?.["changed"]).toEqual(["slots"]);
  expect(commands("prompt.set")).toHaveLength(before);
});

it("sends one prompt.set when the tool wrote a field the view does read", async () => {
  await connected();
  started("+34 000 000 000");
  await settled();
  const before = commands("prompt.set").length;
  calls("findPatient", { name: "Ana", phone: KNOWN });
  await settled();
  const sent = commands("prompt.set").slice(before);
  expect(sent).toHaveLength(1);
  expect(sent[0]?.["name"]).toBe("view");
  expect(String(sent[0]?.["text"])).toContain("Ana");
});

// Recall changes no field, so the re-render must be triggered explicitly.
it("renders again when memory recalls something about the caller", async () => {
  await connected();
  started();
  await settled();
  const before = commands("prompt.set").length;

  gateway.emit(SLUG, CALL, "memory.ops", {
    ops: [
      {
        op: "recall",
        contact: KNOWN,
        query: "quiero cita con la doctora Vidal",
        facts: [{ id: "f1", text: "su médico habitual es la doctora Vidal", category: "médico habitual", score: 0.9 }],
        took_ms: 12,
      },
    ],
    speech_id: "s1",
  });
  await settled();

  const sent = commands("prompt.set").slice(before);
  expect(sent.map((data) => data["name"])).toEqual(["view"]);
  expect(String(sent[0]?.["text"])).toContain("Ofrece primero las horas de su médico habitual");
});

it("sends tools.set with the new visible set when a `when` flips", async () => {
  await connected();
  started();
  await settled();
  calls("freeSlots", { day: "2026-03-02" });
  await settled();
  const visible = commands("tools.set").at(-1)?.["tools"] as { name: string }[];
  expect(visible.map((tool) => tool.name)).toEqual(["freeSlots", "book", "transfer"]);
});

it("answers a tool call whose args fail validation with an error, and runs the next one", async () => {
  await connected();
  started();
  await settled();
  calls("book", { slot: "mañana a las diez" }, "t-bad");
  await settled();
  const refused = commands("tool.result").at(-1);
  expect(refused?.["call_id"]).toBe("t-bad");
  expect(String(refused?.["error"])).toContain("slot must be a object");
  expect(refused?.["output"]).toBeUndefined();

  calls("freeSlots", { day: "2026-03-02" }, "t-good");
  await settled();
  const ran = commands("tool.result").at(-1);
  expect(ran?.["call_id"]).toBe("t-good");
  expect(ran?.["error"]).toBeUndefined();
  // preview: 2 — the model reads two of the three the agenda returned.
  expect(ran?.["output"]).toHaveLength(2);
});

it("writes what the agent logged into the call's log", async () => {
  await connected();
  started();
  await settled();
  calls("freeSlots", { day: "2026-03-02" });
  await settled();
  calls("book", { slot: { when: "2026-03-02 10:00", doctor: "Ruiz" } });
  await settled();
  const [logged] = commands("call.log");
  expect(logged?.["name"]).toBe("appointment.booked");
  expect(logged?.["data"]).toMatchObject({ id: "b-p1" });
});

const ended: string[] = [];

/** Records `onEnd` calls. */
class Despedida extends ClinicaNorte {
  override onEnd(call: { id: string }): void {
    ended.push(call.id);
  }
}

it("runs onEnd and forgets the instance when the call ends", async () => {
  await connected(Despedida);
  started();
  await settled();
  expect(mounted.instanceOf(CALL)).toBeInstanceOf(Despedida);
  gateway.emit(SLUG, CALL, "call.ended", {
    reason: "caller_hung_up",
    ended_by: "caller",
    ended_at: Date.now() / 1000,
    duration_s: 12,
  });
  await settled();
  expect(ended).toEqual([CALL]);
  expect(mounted.instanceOf(CALL)).toBeUndefined();
});

it("reads the medium off call.started, and takes the channel's when the gateway does not say", async () => {
  await connected();
  started(KNOWN, { channel: "web", medium: "text" });
  await settled();
  const written = mounted.instanceOf(CALL)!;
  expect(written.call.medium).toBe("text");
  expect(String(commands("prompt.set").find((data) => data["name"] === "identity")?.["text"])).toContain(
    "You are in a written chat on a website.",
  );

  gateway.emit(SLUG, "CA_2", "call.started", { ...line(KNOWN), channel: "whatsapp" });
  await settled();
  expect(mounted.instanceOf("CA_2")!.call.medium).toBe("text");
});

// `this.call.today` must come from the call, not the machine clock (a different timezone on a box).
it("hands the class the day the call opened", async () => {
  await connected();
  started();
  await settled();

  const serving = mounted.instanceOf(CALL) as unknown as { call?: { today?: string } } | undefined;
  expect(serving?.call?.today).toBe(new Date().toISOString().slice(0, 10));
});

it("tells the class the call was claimed, and claims a code the caller said", async () => {
  await connected();
  started();
  await settled();
  const serving = mounted.instanceOf(CALL) as unknown as { call: { claimed: string | null; claim(code: string): void } };
  expect(serving.call.claimed).toBeNull();

  gateway.emit(SLUG, CALL, "call.claimed", { code: "4821", via: "keypad" });
  await settled();
  expect(serving.call.claimed).toBe("4821");

  serving.call.claim("7305");
  await settled();
  expect(commands("call.claim")).toEqual([{ code: "7305" }]);
});

// A claim changes no field, so the re-render must be triggered explicitly.
class KnowsTheScreen extends ClinicaNorte {
  override render() {
    return this.call.claimed === null ? <p>Read the times out.</p> : <p>The times are on their screen.</p>;
  }
}

it("renders again the moment the call is claimed", async () => {
  await connected(KnowsTheScreen);
  started();
  await settled();
  const before = commands("prompt.set").length;
  gateway.emit(SLUG, CALL, "call.claimed", { code: "4821", via: "keypad" });
  await settled();
  const sent = commands("prompt.set").slice(before);
  expect(sent.map((data) => data["name"])).toEqual(["view"]);
  expect(String(sent[0]?.["text"])).toContain("on their screen");
});

// A view reading the latest turn must re-render when it lands, not one turn late.
class AsksAboutTheTurn extends ClinicaNorte {
  override render() {
    const last = this.call.history.last;
    return last?.who === "user" ? <p>They just said: {last.text}</p> : <p>Nobody has said anything yet.</p>;
  }
}

it("renders again when the caller's turn lands, so a view can be about the turn it answers", async () => {
  await connected(AsksAboutTheTurn);
  started();
  await settled();
  const before = commands("prompt.set").length;

  gateway.emit(SLUG, CALL, "turn.user", { text: "305 555 0101", speech_id: "s1", metrics: {} });
  await settled();

  const sent = commands("prompt.set").slice(before);
  expect(sent.map((data) => data["name"])).toEqual(["view"]);
  expect(String(sent[0]?.["text"])).toBe("They just said: 305 555 0101");
});
