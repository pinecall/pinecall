// A walk's param is picked out of what the visitor typed, never written by the model; the same door picks a table's row and records a walk's sentence once its slots are filled.

import { describe, expect, it } from "vitest";

import { answer, decide, explainOutput, nextLine, pickRow, questionsOf, recordSay, spansOf, thingsOf } from "../../src/server/index.js";

const PAGE = '- form "Book your first visit" [ref=e40]\n  - textbox "Your name" [ref=e41] [empty]';
const BOOK = { name: "book", title: "Book for me", params: { name: { about: "the visitor's name" }, plan: { about: "the plan", oneOf: { family: "Family Care" } } } };
const REQUEST = { message: "I'm Jordan Lee, please book it", path: "/", page: PAGE, walks: [BOOK] };

const answering = (answers: unknown) => async () => new Response(JSON.stringify({ answers }));

describe("the parts of what was typed", () => {
  it("are one to five words in a row, as written, without the commas and quotes around them, an email whole", () => {
    const spans = spansOf('I\'m "Jordan Lee", jordan@lee.dev.');
    expect(spans.slice(0, 4)).toEqual(["I'm", "Jordan", "Lee", "jordan@lee.dev"]);
    expect(spans).toContain("Jordan Lee");
    expect(spans).not.toContain('"Jordan Lee",');
  });

  it("are the choices of a param in the visitor's words, and a list's options those of a param of a list", () => {
    const request = questionsOf(REQUEST, thingsOf(PAGE)) as { questions: Record<string, { criteria: Record<string, string> }> };
    const name = request.questions["param.book.name"]?.criteria ?? {};
    expect(name["none"]).toBe("they did not say");
    expect(Object.values(name)).toContain('"Jordan Lee"');
    expect(request.questions["param.book.plan"]?.criteria).toEqual({ none: "they did not say", family: "Family Care" });
  });
});

describe("a walk decided", () => {
  it("is told the params Jev was sure of: the part it chose, as typed, or the option", async () => {
    const spans = spansOf(REQUEST.message);
    const choice = (value: string, confidence: number) => ({ choice: value, confidence, probabilities: { [value]: confidence } });
    const decided = await decide(REQUEST, {
      key: "k",
      fetch: answering({
        intent: choice("walk", 0.9),
        walk: choice("book", 0.9),
        target: choice("e41", 0.2),
        "param.book.name": choice(`s${spans.indexOf("Jordan Lee")}`, 0.8),
        "param.book.plan": choice("family", 0.3),
      }),
    });
    expect(decided).toEqual({ do: "walk", walk: "book", params: { name: "Jordan Lee" }, confidence: 0.9 });
  });
});

describe("a row picked", () => {
  it("is the one Jev is sure answers the visitor, else none", async () => {
    const rows = ["Tue · 9:00 · Dr. Patel · Cleaning", "Wed · 17:30 · Dr. Okafor · Whitening"];
    expect(await pickRow({ message: "after work", rows }, { key: "k", fetch: answering({ row: { choice: "r1", confidence: 0.9 } }) })).toEqual({ row: 1 });
    expect(await pickRow({ message: "after work", rows }, { key: "k", fetch: answering({ row: { choice: "r1", confidence: 0.2 } }) })).toEqual({ row: null });
  });
});

describe("an output explained", () => {
  it("goes to the gateway's explain door with the voicing, when the site lets its pages explain, and its notes come back checked", async () => {
    const asked: { url: string; body: unknown }[] = [];
    const gateway = async (url: string | URL | Request, init?: RequestInit) => {
      asked.push({ url: String(url), body: JSON.parse(String(init?.body)) });
      return new Response(JSON.stringify({ notes: [{ find: "org lesson", say: "Tu org." }, { find: "", say: "nothing" }, "junk"] }));
    };
    const voicing = { key: "pc", agent: "guia", gateway: "https://gw", env: "sandbox" as const, explain: true };

    expect(await explainOutput({ output: " org lesson · sandbox ", command: "pinecall whoami", language: "es" }, voicing, gateway)).toEqual({ notes: [{ find: "org lesson", say: "Tu org." }] });
    expect(asked[0]).toEqual({ url: "https://gw/v1/agents/guia/explain", body: { output: "org lesson · sandbox", command: "pinecall whoami", language: "es" } });
    await expect(explainOutput({ output: "x" }, { key: "pc", agent: "guia" }, gateway)).rejects.toThrow("explains no output");
  });
});

describe("the dot's next line on a chat it talks to", () => {
  it("is Pinecall's caller's, through the gateway, with the goal, the chat so far and the turns left; refused unless the voicing lets a page talk", async () => {
    const asked: { url: string; body: unknown }[] = [];
    const gateway = async (url: string | URL | Request, init?: RequestInit) => {
      asked.push({ url: String(url), body: JSON.parse(String(init?.body)) });
      return new Response(JSON.stringify({ say: "Hola, quiero dos medialunas.", hangup: false }));
    };
    const voicing = { key: "pc", agent: "guia", gateway: "https://gw", env: "sandbox" as const, next: true };
    const heard = [{ who: "agent" as const, said: "¿Qué te sirvo?" }];

    expect(await nextLine({ goal: " Pedí dos medialunas. ", heard, language: "es" }, voicing, gateway)).toEqual({ say: "Hola, quiero dos medialunas.", hangup: false });
    expect(asked[0]).toEqual({
      url: "https://gw/v1/evals/caller",
      body: { persona: { goal: "Pedí dos medialunas.", style: 'a person writing in a chat, in the language "es": short turns, one or two lines, no narration' }, heard, turns_left: 40 },
    });
    await expect(nextLine({ goal: "x", heard: [] }, { key: "pc", agent: "guia" }, gateway)).rejects.toThrow("talks to no chat");
  });
});

describe("a sentence recorded live", () => {
  const WALKS = { walks: [{ name: "find", title: "Find a time", steps: [{ say: "The soonest is {hit.Day} with {who}.", beats: [], live: true }] }] };
  const gateway = (asked: { url: string; body?: unknown }[]) => async (url: string | URL | Request, init?: RequestInit) => {
    asked.push({ url: String(url), body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    if (String(url).includes("/public/")) return String(url).includes("/public/walks?") ? new Response(JSON.stringify(WALKS)) : new Response("no", { status: 404 });
    return new Response(JSON.stringify({ lines: [{ url: "https://gw/v1/lines/x.mp3", duration_ms: 1200, words: [{ text: "The", start_ms: 0, end_ms: 100 }] }] }));
  };
  const VOICING = { key: "pc", agent: "pip", gateway: "https://gw", env: "sandbox" as const };

  it("is the walk's own sentence, read from what the agent published, its slots filled with the values alone", async () => {
    const asked: { url: string; body?: unknown }[] = [];
    const said = await recordSay({ path: "/book", walk: "find", step: 0, values: { "hit.Day": "Tuesday", who: "Dr. Patel", extra: "never sent" } }, VOICING, gateway(asked));

    expect(said).toEqual({ say: "The soonest is Tuesday with Dr. Patel.", audio: "https://gw/v1/lines/x.mp3", durationMs: 1200, words: [{ text: "The", startMs: 0, endMs: 100 }] });
    expect(asked.map((one) => one.url)).toEqual(["https://gw/v1/agents/pip/public/walks-book?env=sandbox", "https://gw/v1/agents/pip/public/walks?env=sandbox", "https://gw/v1/agents/pip/lines"]);
    expect(asked.at(-1)?.body).toEqual({ texts: ["The soonest is Tuesday with Dr. Patel."] });
  });

  it("is refused for a step that is not a sentence with slots, or a slot with no value, and with no voicing", async () => {
    await expect(recordSay({ path: "/", walk: "find", step: 3, values: {} }, VOICING, gateway([]))).rejects.toThrow("no sentence to record");
    await expect(recordSay({ path: "/", walk: "find", step: 0, values: { who: "x" } }, VOICING, gateway([]))).rejects.toThrow("needs hit.Day, who");
    await expect(answer({ say: { path: "/", walk: "find", step: 0, values: {} } }, { key: "k" })).rejects.toThrow("records no sentence");
    await expect(answer({ nothing: true }, { key: "k" })).rejects.toThrow("{ decide }, { row }, { say }, { read }, { explain } or { next }");
  });
});
