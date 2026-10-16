// Client-side Call: state from the log, and the commands its methods send.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Pinecall, type Agent, type Call, type Tool } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

const KEY = "pk_test";
const AGENT = "clinica-norte";
const CALL = "CA_8f4a2c";

let gateway: FakeGateway;
let pc: Pinecall;
let agent: Agent;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

function ringing(): Record<string, unknown> {
  return {
    channel: "phone",
    from: "+34600123456",
    to: "+34910000001",
    route: { channel: "phone", number: "+34910000001", label: "centralita" },
    caller: { id: "ct_7d1e", phone: "+34600123456", name: "Marta Ruiz" },
    external_id: "SIP-7f3a91",
  };
}

/** Connect one agent and return the call it is handed. */
async function serving(tools: Tool[] = []): Promise<Call> {
  agent = pc.agent(AGENT, { tools });
  await pc.connect();
  const arrived = new Promise<Call>((resolve) => agent.on("call.ringing", (_data, call) => resolve(call as Call)));
  gateway.emit(AGENT, CALL, "call.ringing", ringing());
  return arrived;
}

describe("a call", () => {
  it("knows the line, the caller and its own day off the log alone", async () => {
    const call = await serving();
    expect(call.id).toBe(CALL);
    expect(call.agent).toBe(AGENT);
    expect(call.channel).toBe("phone");
    expect(call.from).toBe("+34600123456");
    expect(call.to).toBe("+34910000001");
    expect(call.contact).toEqual({ id: "ct_7d1e", phone: "+34600123456", name: "Marta Ruiz" });
    expect(call.status).toBe("ringing");
    expect(call.today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("knows whether it is spoken or written once call.started says, and null when it does not", async () => {
    const call = await serving();
    expect(call.medium).toBeNull();
    const started = { channel: "web", direction: "inbound", from: "web", to: AGENT, caller: null, started_at: Date.now() / 1000 };

    gateway.emit(AGENT, CALL, "call.started", { ...started, medium: "text" });
    await vi.waitFor(() => expect(call.medium).toBe("text"));
    gateway.emit(AGENT, CALL, "call.started", started);
    await vi.waitFor(() => expect(call.medium).toBeNull());
  });

  it("runs on the day call.started names when a run pinned one, and on the clock's day otherwise", async () => {
    const call = await serving();
    const started = { channel: "web", direction: "inbound", from: "web", to: AGENT, caller: null, started_at: Date.now() / 1000 };

    gateway.emit(AGENT, CALL, "call.started", { ...started, run: "run_1", today: "2026-09-17" });
    await vi.waitFor(() => expect(call.today).toBe("2026-09-17"));
    gateway.emit(AGENT, CALL, "call.started", started);
    await vi.waitFor(() => expect(call.status).toBe("active"));
    expect(call.today).toBe("2026-09-17");
  });

  it("writes the wire's own key names, never the app's", async () => {
    const call = await serving();
    call.say("Un momento");
    call.setPrompt("view", "El paciente pregunta por una cita");
    call.setState({ patient: "Marta", slot_held: null }, ["patient"]);
    call.setTools([{ name: "book_slot", description: "Reserva", parameters: { type: "object" }, sideEffect: "irreversible", confirm: "Reservo el {slot}, ¿correcto?" }]);
    call.log("slot_search", { took_ms: 41 });
    call.hangup("done");

    await vi.waitFor(() => expect(gateway.commandsOf("call.hangup")).toHaveLength(1));
    expect(gateway.commandsOf("agent.say")[0]?.data).toEqual({ text: "Un momento" });
    expect(gateway.commandsOf("prompt.set")[0]?.data).toEqual({ name: "view", text: "El paciente pregunta por una cita" });
    // State keys are passed through unchanged; only command keys are snake_case.
    expect(gateway.commandsOf("state.set")[0]?.data).toEqual({ state: { patient: "Marta", slot_held: null }, changed: ["patient"] });
    expect(gateway.commandsOf("tools.set")[0]?.data["tools"]).toEqual([
      { name: "book_slot", description: "Reserva", parameters: { type: "object" }, side_effect: "irreversible", confirm: "Reservo el {slot}, ¿correcto?" },
    ]);
    expect(gateway.commandsOf("call.log")[0]?.data).toEqual({ name: "slot_search", data: { took_ms: 41 } });
    expect(gateway.commandsOf("call.hangup")[0]?.call).toBe(CALL);
  });

  it("runs a tool in this process and answers one tool.result against the model's call_id", async () => {
    const call = await serving([
      {
        name: "find_slots",
        description: "Huecos libres",
        parameters: { type: "object", properties: { day: { type: "string" } } },
        run: (args) => ({ slots: ["10:15"], asked: args["day"] }),
      },
    ]);
    gateway.emit(AGENT, call.id, "tool.call", { call_id: "toolu_02", name: "find_slots", arguments: { day: "martes" } });

    await vi.waitFor(() => expect(gateway.commandsOf("tool.result")).toHaveLength(1));
    const answer = gateway.commandsOf("tool.result")[0];
    expect(answer?.data).toMatchObject({ call_id: "toolu_02", name: "find_slots", output: { slots: ["10:15"], asked: "martes" } });
    expect(answer?.data["duration_s"]).toBeTypeOf("number");
  });

  it("answers a tool nobody declared, and a tool that threw, rather than leaving the turn waiting", async () => {
    const call = await serving([
      {
        name: "book_slot",
        description: "Reserva",
        parameters: { type: "object" },
        run: () => {
          throw new Error("el hueco ya no existe");
        },
      },
    ]);
    gateway.emit(AGENT, call.id, "tool.call", { call_id: "toolu_03", name: "cancel_everything", arguments: {} });
    gateway.emit(AGENT, call.id, "tool.call", { call_id: "toolu_04", name: "book_slot", arguments: {} });

    await vi.waitFor(() => expect(gateway.commandsOf("tool.result")).toHaveLength(2));
    const [unknown, threw] = gateway.commandsOf("tool.result");
    expect(unknown?.data["error"]).toMatch(/declares no tool called cancel_everything/);
    expect(threw?.data["error"]).toBe("el hueco ya no existe");
  });

  it("hands a refusal to the model and prints nothing, because the model is the one waiting", async () => {
    const printed = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const nobodyWaiting = vi.fn();
    const call = await serving([
      {
        name: "book_slot",
        description: "Reserva",
        parameters: { type: "object" },
        run: () => {
          throw new Error("ese hueco no está entre las horas libres");
        },
      },
    ]);
    pc.onErrors(nobodyWaiting);

    gateway.emit(AGENT, call.id, "tool.call", { call_id: "toolu_05", name: "book_slot", arguments: {} });

    await vi.waitFor(() => expect(gateway.commandsOf("tool.result")).toHaveLength(1));
    const refusal = gateway.commandsOf("tool.result")[0];
    expect(refusal?.data).toMatchObject({ call_id: "toolu_05", name: "book_slot", error: "ese hueco no está entre las horas libres" });
    expect(refusal?.data["duration_s"]).toBeTypeOf("number");
    expect(nobodyWaiting).not.toHaveBeenCalled();
    expect(printed).not.toHaveBeenCalled();
    printed.mockRestore();
  });

  it("knows the code a page showed once the log says the call claimed it", async () => {
    const call = await serving();
    expect(call.claimed).toBeNull();
    gateway.emit(AGENT, call.id, "call.claimed", { code: "4821", via: "keypad" });
    await vi.waitFor(() => expect(call.claimed).toBe("4821"));
  });

  it("claims a code the caller said with one call.claim", async () => {
    const call = await serving();
    call.claim("4821");
    await vi.waitFor(() => expect(gateway.commandsOf("call.claim")).toHaveLength(1));
    expect(gateway.commandsOf("call.claim")[0]).toMatchObject({ call: CALL, data: { code: "4821" } });
  });

  it("follows the log to active and is forgotten when it ends", async () => {
    const call = await serving();
    expect(agent.calls.live).toEqual([call]);
    gateway.emit(AGENT, call.id, "call.started", { channel: "phone", direction: "inbound", from: "+34600123456", to: "+34910000001", caller: null, started_at: Date.now() / 1000 });
    await vi.waitFor(() => expect(call.status).toBe("active"));
    gateway.emit(AGENT, call.id, "call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: Date.now() / 1000, duration_s: 12 });
    await vi.waitFor(() => expect(call.status).toBe("ended"));
    expect(agent.calls.live).toEqual([]);
  });
});
