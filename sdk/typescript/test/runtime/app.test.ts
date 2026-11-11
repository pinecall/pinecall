// A voice app: the lines it answers, what it adds to its agents' declarations, and what it refuses.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { isVoiceApp, voiceApp } from "../../src/runtime/app.js";

class FrontDesk extends Agent {}
class Billing extends Agent {}
class Greets extends Agent {
  static override greeting = "Hello.";
}

describe("a line", () => {
  it("is a number and the agent that answers it, the number kept as the gateway writes it", () => {
    const app = voiceApp("brightside").line("+1 (415) 555-0134", FrontDesk);
    expect(app.lines).toEqual([{ number: "+14155550134", answers: FrontDesk }]);
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
