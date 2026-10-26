// In a call the model calls a walk with its params: its sentences said with their slots filled, its acts sent to the page one at a time, and a table it read handed back to answer from.

import { CallWorld, runHook, setCall, toolsOf, type Serve } from "@pinecall/agents";
import { describe, expect, it } from "vitest";

import { Tutor, macros } from "../../src/agent/index.js";

const META = { source: "participant" as const, seq: 1 };

class Pip extends Tutor {
  static override macros = macros({
    find: {
      when: "the visitor wants a time for a treatment",
      params: { treatment: { about: "what they want done" } },
      steps: [
        { say: "Let me look for {treatment}.", beats: [] },
        { fill: "Treatment", with: "{treatment}" },
        { press: "Search times" },
        { wait: "Open times", ms: 4000 },
        { read: "Open times", as: "hit" },
        { say: "Never said in a call: the model answers from the table.", beats: [] },
      ],
    },
  });
}

const PAGE = [
  '- search "Find a time" [ref=e10]',
  '  - textbox "Treatment" [ref=e11] [empty]',
  '  - button "Search times" [ref=e12]',
  '- table "Open times" [ref=e20]',
].join("\n");
const FOUND = `${PAGE}\n  - row "Tue, Oct 28 · 9:00 · Dr. Patel" [ref=e21]`;

interface Sent {
  verb: string;
  data: Record<string, unknown>;
}

describe("a walk with params in a call", () => {
  it("is listed with what it takes, and its tool takes them", () => {
    const pip = new Pip();
    pip.page = PAGE;
    expect(pip.seeing()).toContain("- find (params: treatment: what they want done, in the visitor's own words): when the visitor wants a time");
    const runMacro = toolsOf(Pip).find((one) => one.name === "runMacro");
    expect(JSON.stringify(runMacro)).toContain("params");
  });

  it("says its sentences filled, sends its acts in turn, each answered by the page, and hands back the table it read", async () => {
    const pip = new Pip();
    const sent: Sent[] = [];
    const world: CallWorld = new CallWorld({ id: "CA_1", contact: "visitor", channel: "web" }, (verb, data) => {
      sent.push({ verb, data });
      if (verb === "agent.say" && "text" in data) setTimeout(() => world.take("turn.agent", { speech_id: `s${sent.length}`, text: data.text, interrupted: false, metrics: {} }, 0), 0);
      // The page answers each move once it ends, with what it sees then.
      const move = verb === "room.send" && "data" in data ? (data.data as Record<string, unknown>) : undefined;
      if (move?.["type"] === "cursor") {
        const text = move["action"] === "wait" ? FOUND : PAGE;
        setTimeout(() => void runHook(pip, "onEvent", "page.seen", { text, why: "moved" }, META), 0);
      }
    });
    setCall(pip, world);
    await runHook(pip, "onEvent", "page.seen", { text: PAGE, why: "joined" }, META);

    const result = await pip.runMacro("find", { treatment: "a cleaning" });

    const moves = sent.filter((one) => one.verb === "room.send").map((one) => one.data["data"] as Record<string, unknown>);
    expect(moves.filter((one) => one["type"] === "cursor")).toEqual([
      { type: "cursor", action: "type", target: "Treatment", text: "a cleaning" },
      { type: "cursor", action: "press", target: "Search times" },
      { type: "cursor", action: "wait", target: "Open times", ms: 4000 },
    ]);
    expect(sent.filter((one) => one.verb === "agent.say").map((one) => one.data["text"])).toEqual(["Let me look for a cleaning."]);
    expect(result).toContain('row "Tue, Oct 28 · 9:00 · Dr. Patel"');
    expect(result).toContain("Answer the visitor from it");
  });

  it("refuses a value that is not one of a list's options", async () => {
    class Plans extends Tutor {
      static override macros = macros({ plan: { params: { plan: { about: "the plan", one_of: { family: "Family Care" } } }, steps: [{ say: "Here is {plan}.", beats: [] }] } });
    }
    const plans = new Plans();
    plans.page = PAGE;
    await expect(plans.runMacro("plan", { plan: "gold" })).rejects.toThrow("plan is one of family");
  });
});

describe("a walk with params before any call", () => {
  it("is published with its params and acts, its sentences with slots to be said live", async () => {
    const published: Record<string, unknown>[] = [];
    const said: string[] = [];
    const recorded: string[][] = [];
    const serve: Serve = {
      slug: "pip",
      record: async (texts) => {
        recorded.push(texts);
        return texts.map((text, at) => ({ id: `l${at}`, text, url: `https://gw/v1/lines/l${at}.mp3`, durationMs: 1000, voice: "v", timed: true, words: [] }));
      },
      publish: async (name, document) => void published.push({ name, ...document }),
      say: (line) => void said.push(line),
    };
    await Pip.onServe(serve);

    expect(recorded).toEqual([["Never said in a call: the model answers from the table."]]);
    const [walk] = (published[0]?.["walks"] ?? []) as { params: unknown; steps: Record<string, unknown>[] }[];
    expect(walk?.params).toEqual({ treatment: { about: "what they want done" } });
    expect(walk?.steps[0]).toEqual({ say: "Let me look for {treatment}.", beats: [], live: true });
    expect(walk?.steps[2]).toEqual({ press: "Search times" });
    expect(said).toEqual(["walk find · 2 sentences (1 said live) · 4 acts · 0:01 · v"]);
  });
});
