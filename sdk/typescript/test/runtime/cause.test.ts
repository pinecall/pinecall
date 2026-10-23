// A state.set names who made the write: each write of a tool, a hook and an event handler, not only the first.

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, mount, tool, type EventDeclarations } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "desk";
const CALL = "CA_1";

class Desk extends Agent {
  static override events: EventDeclarations = { "slot.released": { from: ["app"] } };

  stage = "identify";
  patient = "";
  slot = "";
  note = "";
  recalled = "";
  opened = "";

  override onCall(): void {
    this.opened = "yes";
    this.stage = "choose";
  }

  override onMemory(): void {
    this.recalled = "ops";
  }

  override onEvent(_name: string, data: Record<string, unknown>): void {
    this.slot = String(data["when"]);
    this.note = "released";
  }

  /** Looks the patient up and moves the stage on. */
  @tool()
  lookUp(): string {
    this.patient = "Ana";
    this.stage = "book";
    return "Ana";
  }
}

/** Writes nothing when a call opens. */
class Quiet extends Agent {
  seen = "";
}

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

async function connected(ctor: new () => Agent = Desk): Promise<void> {
  mount(ctor, { pc, slug: SLUG });
  await pc.connect();
  await settled();
}

async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function started(): void {
  gateway.emit(SLUG, CALL, "call.started", { channel: "web", direction: "inbound", from: "visitor-1", to: SLUG, caller: null, started_at: Date.now() / 1000 });
}

/** What each `state.set` said it changed, and by whom. */
function writes(): { changed: unknown; cause: unknown }[] {
  return gateway
    .commandsOf("state.set")
    .map((command) => ({ changed: command.data["changed"], cause: command.data["cause"] }))
    .filter((write) => write.changed !== undefined);
}

it("names the tool and the model's call on every write the tool makes, not on the first alone", async () => {
  await connected();
  started();
  await settled();
  gateway.emit(SLUG, CALL, "tool.call", { call_id: "toolu_7", name: "lookUp", arguments: {} });
  await settled();

  const by = { kind: "tool", tool: "lookUp", call_id: "toolu_7" };
  expect(writes()).toEqual([
    { changed: ["patient"], cause: by },
    { changed: ["stage"], cause: by },
  ]);
});

it("says a hook wrote what onCall wrote, in the one state.set that carries it", async () => {
  await connected();
  started();
  await settled();

  const [opening] = gateway.commandsOf("state.set");
  expect(opening?.data["cause"]).toEqual({ kind: "hook", hook: "on_call" });
  expect(opening?.data["state"]).toMatchObject({ opened: "yes", stage: "choose" });
});

it("says a hook wrote what onMemory wrote", async () => {
  await connected();
  started();
  await settled();
  gateway.emit(SLUG, CALL, "memory.ops", { ops: [{ op: "recall", facts: [{ text: "prefiere la mañana" }], took_ms: 3 }] });
  await settled();

  expect(writes()).toEqual([{ changed: ["recalled"], cause: { kind: "hook", hook: "on_memory" } }]);
});

it("names the event and its entry on each write the handler makes", async () => {
  await connected();
  started();
  await settled();
  const heard = gateway.emit(SLUG, CALL, "event.received", { name: "slot.released", data: { when: "10:15" }, source: "app" });
  await settled();

  const by = { kind: "event", name: "slot.released", seq: heard.seq };
  expect(writes()).toEqual([
    { changed: ["slot"], cause: by },
    { changed: ["note"], cause: by },
  ]);
});

it("names nobody for a call whose onCall wrote nothing", async () => {
  await connected(Quiet);
  started();
  await settled();

  expect(gateway.commandsOf("state.set")[0]?.data["cause"]).toBeUndefined();
});
