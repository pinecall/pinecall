// A voice app: the lines it answers, what it adds to its agents' declarations, and what it refuses.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { judges, ownJudge } from "../../src/agent/harness.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { isVoiceApp, voiceApp } from "../../src/runtime/app.js";

class FrontDesk extends Agent {}
class Billing extends Agent {}
class Takes extends Agent {
  static takes = "a question about a charge";
}
class Judged extends Agent {
  static override judges = judges({ on: ["grounded"], own: [ownJudge({ name: "offers-a-time", asks: "Did the agent offer a time?" })] });
}
class Greets extends Agent {
  static override greeting = "Hello.";
}

describe("a line", () => {
  it("is a number and the agent that answers it, the number kept as the gateway writes it", () => {
    const app = voiceApp("brightside").line("+1 (415) 555-0134", FrontDesk);
    expect(app.lines).toEqual([{ number: "+14155550134", answers: FrontDesk, team: [] }]);
    expect(app.numbersOf(FrontDesk)).toEqual(["+14155550134"]);
    expect(app.agents()).toEqual([FrontDesk]);
  });

  it("opens the call with its greeting, said by the agent that answers it", () => {
    const app = voiceApp("brightside").line("+14155550134", { answers: FrontDesk, greeting: "Brightside Dental. How can I help?" });
    expect(app.declares(FrontDesk)).toEqual({ greeting: { say: "Brightside Dental. How can I help?" } });
    expect(app.declares(Billing)).toEqual({});
  });

  it("is refused when it is no phone number, no agent, or a line of the app already", () => {
    const app = voiceApp("brightside").line("+14155550134", FrontDesk);
    expect(() => app.line("415 555 0134", FrontDesk)).toThrow(DeclarationRefused);
    expect(() => app.line("+14155550135", {} as never)).toThrow(/answered by an agent class/);
    expect(() => app.line("+1 415 555 0134", Billing)).toThrow(/is a line of brightside already/);
  });

  it("is refused when its agent already opens another line with other words", () => {
    const app = voiceApp("brightside").line("+14155550134", { answers: FrontDesk, greeting: "Brightside Dental." });
    expect(() => app.line("+14155550135", FrontDesk)).toThrow(/both lines open with the same greeting/);
  });

  it("is refused a greeting when the class declares its own", () => {
    const app = voiceApp("brightside").line("+14155550134", { answers: Greets, greeting: "Brightside Dental." });
    expect(() => app.declares(Greets)).toThrow(/keep one of the two/);
  });
});

describe("a line's team", () => {
  it("is the agents its call may pass between, the one that answers first", () => {
    const app = voiceApp("brightside").line("+14155550134", { answers: FrontDesk, team: [Takes] });
    expect(app.teamOf(FrontDesk)).toEqual([FrontDesk, Takes]);
    expect(app.teamOf(Takes)).toEqual([FrontDesk, Takes]);
    expect(app.agents()).toEqual([FrontDesk, Takes]);
    expect(app.teamOf(Billing)).toEqual([]);
  });

  it("is refused a member that says nothing of what it takes", () => {
    expect(() => voiceApp("brightside").line("+14155550134", { answers: FrontDesk, team: [Billing] })).toThrow(/says nothing of what it takes/);
  });
});

describe("a line that chooses", () => {
  it("is bound to its fallback and hands its function to the mount of that agent", () => {
    const choose = (): typeof Takes => Takes;
    const app = voiceApp("brightside").line("+14155550134", { answers: choose, fallback: FrontDesk, team: [Takes] });
    expect(app.lines[0]?.answers).toBe(FrontDesk);
    expect(app.choosing(FrontDesk)).toBe(choose);
    expect(app.choosing(Takes)).toBeUndefined();
  });

  it("is refused without a fallback, or without a team to choose among", () => {
    expect(() => voiceApp("brightside").line("+14155550134", { answers: () => Takes, team: [Takes] })).toThrow(/names its fallback/);
    expect(() => voiceApp("brightside").line("+14155550134", { answers: () => Takes, fallback: FrontDesk })).toThrow(/names none/);
  });
});

describe("what the app hears", () => {
  const entry = { seq: 1, ts: 0, ephemeral: false, call: "CA_1", agent: "front-desk" };

  it("is an entry of a call by its type, and a line an agent logged by its name", async () => {
    const heard: unknown[] = [];
    const app = voiceApp("brightside")
      .on("call.ended", (call, data) => void heard.push(["ended", call.id, data["reason"]]))
      .on("visit.booked", (call, data) => void heard.push(["booked", call.agent, data["id"]]));
    await app.heard({ ...entry, type: "call.ended", data: { reason: "caller_hung_up" } });
    await app.heard({ ...entry, type: "custom", data: { name: "visit.booked", data: { id: "v-1" } } });
    await app.heard({ ...entry, type: "turn.user", data: { text: "hello" } });
    expect(heard).toEqual([["ended", "CA_1", "caller_hung_up"], ["booked", "front-desk", "v-1"]]);
  });

  it("goes on to the next handler when one throws, and says which", async () => {
    const failed: string[] = [];
    let ran = false;
    const app = voiceApp("brightside")
      .on("call.ended", () => { throw new Error("the database is down"); })
      .on("call.ended", () => void (ran = true));
    await app.heard({ ...entry, type: "call.ended", data: {} }, (name, error) => failed.push(`${name}: ${error.message}`));
    expect(failed).toEqual(["call.ended: the database is down"]);
    expect(ran).toBe(true);
  });
});

describe("a rule", () => {
  it("is every agent's, with a judge that asks of each call whether it was kept", () => {
    const app = voiceApp("brightside").line("+14155550134", FrontDesk).rule("Never quote a price that is not in the price list.");
    expect(app.rules).toEqual(["Never quote a price that is not in the price list."]);
    expect(app.declares(FrontDesk).judges).toEqual({
      on: [],
      own: [expect.objectContaining({ name: "app-rule-1", question: expect.stringContaining("Never quote a price") })],
    });
    expect(app.declares(Billing)).toEqual({});
  });

  it("keeps the judges the class declares beside its own", () => {
    const app = voiceApp("brightside").line("+14155550134", Judged).rule("Read a time back before booking it.");
    const declared = app.declares(Judged).judges;
    expect(declared?.on).toEqual(["grounded"]);
    expect(declared?.own?.map((judge) => judge.name)).toEqual(["offers-a-time", "app-rule-1"]);
  });
});

describe("silence", () => {
  it("is what every agent of the app says to a caller who went quiet", () => {
    const app = voiceApp("brightside").line("+14155550134", FrontDesk).silence({ after: "8s", say: "Are you still there?", times: 2 });
    expect(app.declares(FrontDesk)).toEqual({ idle: { says: ["Are you still there?"], afterS: 8, times: 2 } });
    expect(app.declares(Billing)).toEqual({});
  });

  it("is refused without the words, or with a wait that is no number of seconds", () => {
    const app = voiceApp("brightside");
    expect(() => app.silence({ after: "soon", say: "Hello?" })).toThrow(DeclarationRefused);
    expect(() => app.silence({ after: 8, say: " " })).toThrow(DeclarationRefused);
  });
});

describe("its timezone", () => {
  it("is the zone every agent of the app reads its day and its clock in", () => {
    const app = voiceApp("brightside", { timezone: "America/Los_Angeles" }).line("+14155550134", FrontDesk);
    expect(app.declares(FrontDesk)).toEqual({ timezone: "America/Los_Angeles" });
    expect(app.declares(Billing)).toEqual({});
  });

  it("is refused where it was typed when it is no IANA zone", () => {
    expect(() => voiceApp("brightside", { timezone: "Pacific Time" })).toThrow(/an IANA zone/);
  });
});

describe("a voice app", () => {
  it("is named like its project's folder", () => {
    expect(() => voiceApp("Brightside Dental")).toThrow(/lowercase letters, digits and dashes/);
  });

  it("is known by its brand, whichever copy of the package made it", () => {
    expect(isVoiceApp(voiceApp("brightside"))).toBe(true);
    expect(isVoiceApp({ name: "brightside" })).toBe(false);
  });
});
