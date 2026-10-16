// Call events in and verbs out, against a fake gateway.

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, changes, mount, state, type EventDeclarations, type EventMeta, type Mounted } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "front-desk";
const CALL = "CA_1";
const CALLER = "sip_+34600000001";

/** Accepts one app event and one browser event. */
class FrontDesk extends Agent {
  static override events: EventDeclarations = {
    "slot.released": { from: ["app"] },
    "ui.viewing": { from: ["participant"] },
  };

  web = true;

  @state({ visibility: "public" })
  slot?: string;

  // Bare `@state` sends no visibility (the wire defaults to tenant). Required here because
  // another field is decorated.
  @state notes?: string;

  override async onEvent(name: string, data: Record<string, unknown>, _meta: EventMeta): Promise<void> {
    // A real hook awaits its backend; a tick here is enough to interleave two events.
    await new Promise((resolve) => setTimeout(resolve, 2));
    if (name === "slot.released") this.slot = String(data["when"]);
  }
}

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mounted = mount(FrontDesk, { pc, slug: SLUG });
  await pc.connect();
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

/** Let pending socket work settle. */
async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function started(): void {
  gateway.emit(SLUG, CALL, "call.started", {
    channel: "web",
    direction: "inbound",
    from: "visitor-1",
    to: "front-desk",
    caller: null,
    started_at: Date.now() / 1000,
  });
}

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

function instance(): FrontDesk {
  const agent = mounted.instanceOf(CALL);
  expect(agent).toBeDefined();
  return agent as FrontDesk;
}

it("declares a decorated field public and leaves an undecorated one to the wire's default", () => {
  const config = commands("agent.configure")[0]?.["config"] as { state_fields?: { name: string; visibility: string }[] };
  expect(config.state_fields).toEqual([{ name: "slot", visibility: "public" }]);
  expect(config.state_fields?.some((field) => field.name === "notes")).toBe(false);
});

it("declares its two events with the sources each accepts", () => {
  const config = commands("agent.configure")[0]?.["config"] as { events?: { name: string; from: string[] }[] };
  expect(config.events).toEqual([
    { name: "slot.released", from: ["app"] },
    { name: "ui.viewing", from: ["participant"] },
  ]);
});

it("hands an event declared from app to onEvent, authored by the event and caused by it in the log", async () => {
  started();
  await settled();
  gateway.emit(SLUG, CALL, "event.received", { name: "slot.released", data: { when: "10:15" }, source: "app" });
  await settled();

  expect(instance().slot).toBe("10:15");
  const written = changes(instance()).find((change) => change.field === "slot");
  expect(written?.author).toBe("event:slot.released");
  const cause = commands("call.log").find((data) => data["name"] === "state.cause");
  expect(cause?.["data"]).toEqual({ field: "slot", kind: "event", name: "slot.released", seq: 1 });
});

it("never hands the hook a name that source may not send, and warns once and not twice", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  started();
  await settled();
  const heard: string[] = [];
  instance().on("event", (event) => heard.push(event.name));
  gateway.emit(SLUG, CALL, "event.received", { name: "ui.viewing", data: {}, source: "app" });
  gateway.emit(SLUG, CALL, "event.received", { name: "ui.viewing", data: {}, source: "app" });
  await settled();

  expect(heard).toEqual([]);
  expect(warned).toHaveBeenCalledTimes(1);
  warned.mockRestore();
});

it("tells an in-process observer about an event the hook accepted", async () => {
  started();
  await settled();
  const heard: { name: string; meta: EventMeta }[] = [];
  instance().on("event", (event) => heard.push({ name: event.name, meta: event.meta }));
  gateway.emit(SLUG, CALL, "event.received", { name: "ui.viewing", data: { page: "prices" }, source: "participant", identity: CALLER });
  await settled();

  expect(heard).toEqual([{ name: "ui.viewing", meta: { source: "participant", identity: CALLER, seq: 1 } }]);
});

it("reflects who joined, who is speaking and who left in call.room", async () => {
  started();
  await settled();
  gateway.emit(SLUG, CALL, "participant.joined", { identity: CALLER, kind: "caller", name: "Ana", attributes: {} });
  gateway.emit(SLUG, CALL, "participant.joined", { identity: "sup_1", kind: "supervisor", attributes: {} });
  gateway.emit(SLUG, CALL, "participant.speaking", { identity: CALLER, speaking: true });
  await settled();

  const room = instance().call.room;
  expect(room.caller?.name).toBe("Ana");
  expect(room.caller?.speaking).toBe(true);
  expect(room.has("supervisor")).toBe(true);

  gateway.emit(SLUG, CALL, "participant.left", { identity: "sup_1", reason: "client_initiated" });
  await settled();
  expect(room.has("supervisor")).toBe(false);
  expect(room.participants.map((one) => one.identity)).toEqual([CALLER]);
});

it("sends exactly its own command for invite, mute, remove and send", async () => {
  started();
  await settled();
  const call = instance().call;
  call.room.invite("+34 600 111 222", { kind: "sip" });
  call.participant(CALLER).mute();
  call.participant(CALLER).remove();
  call.send("pinecall.ui", { card: "prices" }, { to: CALLER });
  await settled();

  expect(commands("room.invite")).toEqual([{ to: "+34 600 111 222", kind: "sip" }]);
  expect(commands("participant.mute")).toEqual([{ identity: CALLER }]);
  expect(commands("participant.remove")).toEqual([{ identity: CALLER }]);
  expect(commands("room.send")).toEqual([{ topic: "pinecall.ui", data: { card: "prices" }, to: CALLER }]);
});

it("sends agent.reply and resolves when the turn it lands as arrives", async () => {
  started();
  await settled();
  let settledWith: boolean | null = null;
  const spoken = instance()
    .reply("tell them a slot at 10:15 opened", { allowInterruptions: false })
    .then((ok) => (settledWith = ok));
  await settled();

  expect(commands("agent.reply")).toEqual([
    { instructions: "tell them a slot at 10:15 opened", allow_interruptions: false },
  ]);
  expect(settledWith).toBeNull();

  gateway.emit(SLUG, CALL, "turn.agent", { speech_id: "s1", text: "Se ha liberado una cita a las 10:15.", interrupted: false, metrics: {} });
  await spoken;
  expect(settledWith).toBe(true);
});

it("sends agent.say with the words themselves and resolves on the turn", async () => {
  started();
  await settled();
  const spoken = instance().say("Un momento, por favor.");
  gateway.emit(SLUG, CALL, "turn.agent", { speech_id: "s1", text: "Un momento, por favor.", interrupted: false, metrics: {} });

  expect(await spoken).toBe(true);
  expect(commands("agent.say")).toEqual([{ text: "Un momento, por favor." }]);
});

it("reduces the caller's turn and the agent's into the call's history", async () => {
  started();
  await settled();
  gateway.emit(SLUG, CALL, "turn.user", { speech_id: "s1", text: "Quiero una cita.", metrics: {} });
  gateway.emit(SLUG, CALL, "turn.agent", { speech_id: "s1", text: "¿Para qué día?", interrupted: false, metrics: {} });
  await settled();

  const history = instance().call.history;
  expect(history.turns.map((turn) => [turn.who, turn.text])).toEqual([
    ["user", "Quiero una cita."],
    ["agent", "¿Para qué día?"],
  ]);
  expect(history.last?.speechId).toBe("s1");

  history.collapse("pidió cita y se le preguntó el día");
  expect(history.length).toBe(0);
  expect(history.summary).toBe("pidió cita y se le preguntó el día");
});

// Serial dispatch keeps each hook's writes attributed to its own event.
it("dispatches two events one after another, so each write names its own event as the cause", async () => {
  started();
  await settled();
  gateway.emit(SLUG, CALL, "event.received", { name: "slot.released", data: { when: "10:15" }, source: "app" });
  gateway.emit(SLUG, CALL, "event.received", { name: "slot.released", data: { when: "11:00" }, source: "app" });
  await settled();

  expect(instance().slot).toBe("11:00");
  const causes = commands("call.log")
    .filter((data) => data["name"] === "state.cause")
    .map((data) => (data["data"] as { seq: number }).seq);
  expect(causes).toEqual([1, 2]);
});
