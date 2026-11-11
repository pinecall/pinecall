// A team of agents on one call: the transfers each is offered, and the call passed from one to the other on the wire.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { describe as describe_ } from "../../src/agent/docstrings.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { mount } from "../../src/runtime/connect.js";
import { answeredBy, mateNamed, MOST_PASSES, teamTools, transfersOf, type Team } from "../../src/runtime/handoff.js";

import Billing from "./team/billing.js";
import FrontDesk from "./team/front-desk.js";
import Twice from "./team/twice.js";

const KEY = "pk_test";
const CALL = "CA_1";

for (const [ctor, name] of [[FrontDesk, "front-desk"], [Billing, "billing"], [Twice, "twice"]] as const) {
  const file = fileURLToPath(new URL(`./team/${name}.ts`, import.meta.url));
  describe_(ctor, readFileSync(file, "utf8"), file);
}

const TEAM: Team = new Map<new () => Agent, string>([
  [FrontDesk, "front-desk"],
  [Billing, "billing"],
]);

describe("the transfers a team's agent is offered", () => {
  it("are one tool per teammate that says what it takes, never one to itself", () => {
    const offered = transfersOf(FrontDesk, TEAM);
    expect(offered.map((spec) => spec.name)).toEqual(["transfer_to_billing"]);
    expect(offered[0]?.description).toContain("a question about a charge, an invoice or a refund");
    expect(mateNamed("transfer_to_front_desk", TEAM)).toBe(FrontDesk);
    expect(mateNamed("balance", TEAM)).toBeUndefined();
  });

  it("are declared with every member's own tools, each name once", () => {
    expect(teamTools(TEAM).map((spec) => spec.name).sort()).toEqual(["balance", "disputeCharge", "transfer_to_billing", "transfer_to_front_desk"]);
  });

  it("are refused when two members declare a tool of one name", () => {
    const clash: Team = new Map<new () => Agent, string>([[Billing, "billing"], [Twice, "twice"]]);
    expect(() => teamTools(clash)).toThrow(DeclarationRefused);
  });
});

describe("a line that chooses who answers", () => {
  const line = { id: "CA_1", contact: "+34600000001" };

  it("is served by the agent of the team its function names, and by the one it is bound to when it names nobody", async () => {
    expect(await answeredBy(() => Billing, line, FrontDesk, TEAM)).toEqual({ agent: Billing });
    expect(await answeredBy(async () => undefined, line, FrontDesk, TEAM)).toEqual({ agent: FrontDesk });
  });

  it("falls back, saying why, when the function throws, is late or names an agent of no team", async () => {
    const threw = await answeredBy(() => { throw new Error("the agenda is down"); }, line, FrontDesk, TEAM);
    expect(threw).toEqual({ agent: FrontDesk, why: "answers threw: the agenda is down" });
    const stranger = await answeredBy(() => Twice, line, FrontDesk, TEAM);
    expect(stranger.agent).toBe(FrontDesk);
    expect(stranger.why).toContain("not of the line's team");
    const late = await answeredBy(() => new Promise<undefined>(() => {}), line, FrontDesk, TEAM);
    expect(late.why).toContain("took more than");
  });
});

describe("a call a line routed", () => {
  it("opens on the agent its function chose, with a line on the log", async () => {
    const gateway = await FakeGateway.start({ apiKey: KEY });
    const pc = new Pinecall({ url: gateway.url, apiKey: KEY });
    pc.onErrors(() => {});
    mount(FrontDesk, { pc, slug: "front-desk", team: TEAM, answers: () => Billing });
    await pc.connect();
    gateway.emit("front-desk", CALL, "call.started", { channel: "phone", direction: "inbound", from: "+34600000001", to: "+34910000000", caller: null, started_at: Date.now() / 1000 });
    for (let turn = 0; turn < 40; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
    const tools = gateway.commandsOf("tools.set").at(-1)?.data["tools"] as { name: string }[];
    expect(tools.map((spec) => spec.name).sort()).toEqual(["balance", "transfer_to_front_desk"]);
    expect(gateway.commandsOf("call.log").map((command) => command.data)).toContainEqual(expect.objectContaining({ name: "routed", data: { to: "billing" } }));
    pc.close();
    await gateway.close();
  });
});

describe("a call passed to a teammate", () => {
  let gateway: FakeGateway;
  let pc: Pinecall;

  beforeEach(async () => {
    gateway = await FakeGateway.start({ apiKey: KEY });
    pc = new Pinecall({ url: gateway.url, apiKey: KEY });
    pc.onErrors(() => {});
    mount(FrontDesk, { pc, slug: "front-desk", team: TEAM });
    await pc.connect();
    await settled();
    gateway.emit("front-desk", CALL, "call.started", { channel: "phone", direction: "inbound", from: "+34600000001", to: "+34910000000", caller: null, started_at: Date.now() / 1000 });
    await settled();
  });

  afterEach(async () => {
    pc.close();
    await gateway.close();
  });

  async function settled(): Promise<void> {
    for (let turn = 0; turn < 30; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
  }

  function commands(type: string): Record<string, unknown>[] {
    return gateway.commandsOf(type).map((command) => command.data);
  }

  function visible(): string[] {
    return (commands("tools.set").at(-1)?.["tools"] as { name: string }[]).map((spec) => spec.name).sort();
  }

  async function called(name: string, args: Record<string, unknown>, id: string): Promise<Record<string, unknown> | undefined> {
    gateway.emit("front-desk", CALL, "tool.call", { call_id: id, name, arguments: args });
    await settled();
    return commands("tool.result").find((result) => result["callId"] === id || result["call_id"] === id);
  }

  it("opens the tools of the one that answered, and the transfer to its teammate", () => {
    expect(visible()).toEqual(["disputeCharge", "transfer_to_billing"]);
  });

  it("is served by the teammate from the pass on: its tools, its state, what it was handed, and a line on the log", async () => {
    await called("disputeCharge", { invoice: "inv_7" }, "t1");
    expect(visible()).toEqual(["balance", "transfer_to_front_desk"]);
    expect(commands("state.set").at(-1)?.["state"]).toMatchObject({ invoice: "inv_7" });
    expect(commands("call.log").at(-1)).toMatchObject({ name: "handoff", data: { from: "front-desk", to: "billing", invoice: "inv_7" } });
    const balance = await called("balance", {}, "t2");
    expect(balance).toMatchObject({ output: 42 });
  });

  it("is passed by the model through the transfer tool, and no more times than a call is passed", async () => {
    await called("transfer_to_billing", { reason: "a charge" }, "t1");
    expect(visible()).toEqual(["balance", "transfer_to_front_desk"]);
    for (let pass = 1; pass < MOST_PASSES; pass++) {
      await called(pass % 2 === 1 ? "transfer_to_front_desk" : "transfer_to_billing", {}, `p${pass}`);
    }
    const refused = await called("transfer_to_front_desk", {}, "last");
    expect(JSON.stringify(refused)).toContain(`passed ${MOST_PASSES} times already`);
  });
});
