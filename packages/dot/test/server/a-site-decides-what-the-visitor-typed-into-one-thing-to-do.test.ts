// A site's server decides what the visitor typed to the dot: one request with three questions, and their answers made one thing to do, never a guess.

import { describe, expect, it } from "vitest";

import { decide, decisionFrom, questionsOf, thingsOf } from "../../src/server/index.js";

const PAGE = [
  '- region "Plans" [ref=e2]',
  '  - article "Team plan" [ref=e3]',
  '  - text "$99 / month"',
  '- region "Compare the plans" [ref=e5]',
].join("\n");
const REQUEST = { message: "where do I see what each plan includes?", path: "/pricing", page: PAGE, walks: [{ name: "plans", title: "Which plan is yours", when: "the visitor asks what it costs" }] };

const answer = (choice: string, confidence: number, probabilities: Record<string, number> = { [choice]: confidence }) => ({ choice, confidence, probabilities });

describe("what the model is asked", () => {
  it("is every named thing of the page by its ref, the page's walks, and what kind of thing they want", () => {
    const request = questionsOf(REQUEST, thingsOf(PAGE)) as { state: string[]; questions: Record<string, { criteria: Record<string, string> }> };

    expect(Object.keys(request.questions).sort()).toEqual(["intent", "target", "walk"]);
    expect(request.questions["target"]?.criteria).toEqual({ e2: 'region "Plans"', e3: 'article "Team plan"', e5: 'region "Compare the plans"' });
    expect(Object.keys(request.questions["intent"]?.criteria ?? {})).toEqual(["walk", "show", "talk", "none"]);
    expect(request.state[0]).toContain('typed to its guide: "where do I see what each plan includes?"');
  });

  it("offers no walk on a page that has none, and at most 255 things, the sections first", () => {
    const bare = questionsOf({ ...REQUEST, walks: [] }, thingsOf(PAGE)) as { questions: Record<string, { criteria: Record<string, string> }> };
    expect(Object.keys(bare.questions).sort()).toEqual(["intent", "target"]);
    expect(Object.keys(bare.questions["intent"]?.criteria ?? {})).not.toContain("walk");

    const crowded = [...Array.from({ length: 300 }, (_, at) => `- link "Link ${at}" [ref=e${at + 10}]`), '- region "Footer" [ref=e999]'].join("\n");
    const things = thingsOf(crowded);
    expect(things).toHaveLength(255);
    expect(things.map((thing) => thing.ref)).toContain("e999");
  });
});

describe("what the answers come to", () => {
  it("is the walk or the thing, whichever is surer when acting is more likely than not", () => {
    const acting = { walk: 0.5, show: 0.49, talk: 0, none: 0.01 };
    expect(decisionFrom({ intent: answer("walk", 0.25, acting), walk: answer("plans", 0.6), target: answer("e5", 0.94) })).toEqual({ do: "show", target: "e5", confidence: 0.94 });
    expect(decisionFrom({ intent: answer("walk", 0.9, { walk: 0.9, show: 0.1 }), walk: answer("plans", 0.8), target: answer("e5", 0.3) })).toEqual({ do: "walk", walk: "plans", confidence: 0.8 });
  });

  it("does nothing rather than guess under the threshold, and offers the agent for a question a person answers", () => {
    expect(decisionFrom({ intent: answer("show", 0.9, { show: 0.95 }), target: answer("e3", 0.3) })).toEqual({ do: "none", confidence: 0.9 });
    expect(decisionFrom({ intent: answer("talk", 0.8, { talk: 0.8, none: 0.2 }) })).toEqual({ do: "talk", confidence: 0.8 });
    expect(decisionFrom({ intent: answer("none", 0.7, { talk: 0.2, none: 0.7 }) })).toEqual({ do: "none", confidence: 0.7 });
  });

  it("asks OpenRouter's Decisions API with the server's key, and never answers a thing that is not on the page", async () => {
    const asked: { url: string; init: RequestInit }[] = [];
    const replying = (answers: unknown) => async (url: string | URL | Request, init?: RequestInit) => {
      asked.push({ url: String(url), init: init ?? {} });
      return new Response(JSON.stringify({ answers }));
    };

    const shown = await decide(REQUEST, { key: "k", fetch: replying({ intent: answer("show", 0.9, { show: 0.9 }), target: answer("e5", 0.9) }) });
    expect(shown).toEqual({ do: "show", target: "e5", confidence: 0.9 });
    expect(asked[0]?.url).toBe("https://openrouter.ai/api/alpha/decisions");
    expect((asked[0]?.init.headers as Record<string, string>)["authorization"]).toBe("Bearer k");

    const strange = await decide(REQUEST, { key: "k", fetch: replying({ intent: answer("show", 0.9, { show: 0.9 }), target: answer("e77", 0.99) }) });
    expect(strange).toEqual({ do: "none", confidence: 0 });
    await expect(decide(REQUEST, { key: "k", fetch: async () => new Response("no", { status: 402 }) })).rejects.toThrow("402");
  });
});
