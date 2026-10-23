/** The live view folded from events: calls counted, the state with what changed marked, the text clipped to the terminal. */

import type { CamelEvent } from "@pinecall/agents/client";
import { describe, expect, it } from "vitest";

import { absorb, draw, screenFor, statePanel } from "../../src/dev/screen.js";

const event = (type: string, data: Record<string, unknown>): CamelEvent => ({ type, data }) as unknown as CamelEvent;

describe("the view", () => {
  it("counts calls and keeps the state the last change named", () => {
    let screen = screenFor("front-desk", "https://gateway.test");
    screen = absorb(screen, event("call.started", {}));
    screen = absorb(screen, event("state.changed", { state: { patient: "Ana", slot: null }, changed: ["patient"] }));
    expect(screen.calls).toBe(1);
    expect(screen.state).toEqual({ patient: "Ana", slot: null });
    expect(screen.events).toHaveLength(2);
  });

  it("a refusal the gateway sends the app — a kill — is a line of the transcript", () => {
    const screen = absorb(screenFor("front-desk", "https://gateway.test"), event("error", { code: "killed", message: "front-desk was killed by ana" }));
    expect(screen.transcript.map((line) => line.text)).toEqual(["front-desk was killed by ana"]);
  });

  it("the state panel marks what changed, and says when there is none", () => {
    expect(statePanel({}, [])).toEqual(["  (no state yet)"]);
    expect(statePanel({ patient: "Ana", notes: "x".repeat(80) }, ["patient"])).toEqual(["● patient: Ana", `  notes: ${"x".repeat(59)}…`]);
  });

  it("is drawn clipped to the terminal's width, raw as events when asked", () => {
    const screen = absorb(screenFor("front-desk", "https://gateway.test"), event("call.started", {}));
    const drawn = draw(screen, 30, 20).split("\n");
    expect(drawn[0]).toBe("pinecall front-desk ");
    expect(drawn.every((one) => one.length <= 20)).toBe(true);
    expect(draw(screen, 30, 200, true)).toContain('{"type":"call.started","data":{}}');
  });
});
