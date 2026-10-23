/** A serve entry's stdout read: an entry a line, a registration answering its app, anything else passed on as it came. */

import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import { Relay, servedByTheGateway, servingFrom, type EventLine } from "../../src/dev/serving.js";

const line = (type: string, agent: string, data: Record<string, unknown> = {}): string => `${JSON.stringify({ type, agent, data })}\n`;

describe("the lines", () => {
  it("a registration answers its app, a later one replaces it, every entry reaches a listener", async () => {
    const lines = new PassThrough();
    const other = new PassThrough();
    const serving = servingFrom(lines, other);
    const heard: EventLine[] = [];
    const stop = serving.onEvent((one) => heard.push(one));
    const first = serving.registered("front-desk");
    lines.write("a log line of the tenant's\n");
    lines.write(line("agent.registered", "front-desk", { app: "app_1" }));
    expect(await first).toBe("app_1");
    lines.write(line("agent.registered", "front-desk", { app: "app_2" }));
    lines.write(line("call.started", "front-desk"));
    await new Promise((settled) => setImmediate(settled));
    expect(serving.app("front-desk")).toBe("app_2");
    expect(await serving.registered("front-desk")).toBe("app_2");
    expect(heard.map((one) => one.type)).toEqual(["agent.registered", "agent.registered", "call.started"]);
    stop();
    lines.write(line("call.ended", "front-desk"));
    await new Promise((settled) => setImmediate(settled));
    expect(heard).toHaveLength(3);
    expect(String(other.read())).toBe("a log line of the tenant's\n");
  });

  it("JSON that is no entry is passed on, not taken for one", async () => {
    const lines = new PassThrough();
    const other = new PassThrough();
    servingFrom(lines, other);
    lines.write('{"level":"info"}\n');
    await new Promise((settled) => setImmediate(settled));
    expect(String(other.read())).toBe('{"level":"info"}\n');
  });

  it("an agent the gateway serves names no app", () => {
    expect(servedByTheGateway("front-desk").app()).toBeUndefined();
  });
});

describe("the relay", () => {
  it("a listener hears the entry answering now, and the next one once followed; the app read is the current one's", async () => {
    const first = servingFrom(new PassThrough(), new PassThrough());
    const second = new PassThrough();
    const relay = new Relay(first);
    const heard: string[] = [];
    relay.onEvent((one) => heard.push(`${one.type}@${one.data["app"]}`));
    const next = servingFrom(second, new PassThrough());
    second.write(line("agent.registered", "front-desk", { app: "app_2" }));
    await new Promise((settled) => setImmediate(settled));
    expect(heard).toEqual([]);
    expect(relay.app("front-desk")).toBeUndefined();
    relay.follow(next);
    second.write(line("call.started", "front-desk", { app: "app_2" }));
    await new Promise((settled) => setImmediate(settled));
    expect(heard).toEqual(["call.started@app_2"]);
    expect(relay.app("front-desk")).toBe("app_2");
    expect(await relay.registered("front-desk")).toBe("app_2");
  });
});
