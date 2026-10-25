// The mood follows the call (opening thinks, a live call follows the agent's state), and every number eases, never jumps.

import { describe, expect, it } from "vitest";

import { BLINK_S, eased, lidAt, moodOf, nextBlink } from "../../src/face/motion.js";
import { aRoom } from "../a-room.js";

describe("the mood", () => {
  const { state } = aRoom();

  it("rests before a call, thinks while one opens, and rests once it is over", () => {
    expect(moodOf(state)).toBe("idle");
    expect(moodOf({ ...state, phase: "opening" })).toBe("thinking");
    expect(moodOf({ ...state, phase: "ended" })).toBe("idle");
  });

  it("follows the agent's own state in a live call, and listens when the state says anything else", () => {
    const live = (agent: typeof state.log.agent_state) => moodOf({ ...state, phase: "live", log: { ...state.log, agent_state: agent } });

    expect(live("speaking")).toBe("speaking");
    expect(live("thinking")).toBe("thinking");
    expect(live("listening")).toBe("listening");
    expect(live(null)).toBe("listening");
  });

  it("hears while the caller speaks, as the room hears them or their words come in, until the agent thinks", () => {
    const live = { ...state, phase: "live" as const, log: { ...state.log, agent_state: "listening" as const } };

    expect(moodOf({ ...live, speaking: { ...live.speaking, user: true } })).toBe("hearing");
    expect(moodOf({ ...live, log: { ...live.log, live: { ...live.log.live, user: "Can I come" } } })).toBe("hearing");
    expect(moodOf({ ...live, speaking: { ...live.speaking, user: true }, log: { ...live.log, agent_state: "thinking" } })).toBe("thinking");
  });
});

describe("the easing", () => {
  it("moves toward the target without passing it, and opens faster than it closes", () => {
    const opened = eased(0, 1, 0.016, 0.035, 0.075);
    const closed = 1 - eased(1, 0, 0.016, 0.035, 0.075);

    expect(opened).toBeGreaterThan(0);
    expect(opened).toBeLessThan(1);
    expect(opened).toBeGreaterThan(closed);
    expect(eased(0.4, 0.4, 0.016, 0.035, 0.075)).toBe(0.4);
  });
});

describe("the blink", () => {
  it("shuts the lids halfway through and opens them again by the end", () => {
    expect(lidAt(0)).toBe(1);
    expect(lidAt(BLINK_S / 2)).toBeCloseTo(0.1, 5);
    expect(lidAt(BLINK_S)).toBe(1);
  });

  it("comes every 2.5 to 6 seconds, and now and then twice in a row", () => {
    expect(nextBlink(0.1)).toBe(0.18);
    expect(nextBlink(0.18)).toBe(2.5);
    expect(nextBlink(0.999)).toBeLessThanOrEqual(6);
  });
});
