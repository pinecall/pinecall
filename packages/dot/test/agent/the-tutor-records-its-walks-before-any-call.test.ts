// Before any call, a tutor records each of its macros in the agent's voice and publishes them as walks; a walk the visitor played reaches its view.

import { runHook, type Serve } from "@pinecall/agents";
import { describe, expect, it } from "vitest";

import { Tutor, macros } from "../../src/agent/index.js";

const META = { source: "participant" as const, seq: 1 };

class Pip extends Tutor {
  static override macros = macros({
    tour: {
      title: "Site tour",
      when: "the visitor asks to be shown around",
      steps: [
        { say: "Up here are our services.", beats: [{ word: "services.", do: "point", find: ["link", "Services"] }] },
        { say: "That is all.", beats: [] },
      ],
    },
  });
}

/** A serve that records each text as a line of 1 s with one word a sentence, and keeps what was published and said. */
function aServe(): { serve: Serve; published: Record<string, unknown>[]; said: string[]; asked: string[][] } {
  const published: Record<string, unknown>[] = [];
  const said: string[] = [];
  const asked: string[][] = [];
  const serve: Serve = {
    slug: "pip",
    record: async (texts) => {
      asked.push(texts);
      return texts.map((text, at) => ({ id: `l${at}`, text, url: `https://gw/v1/lines/l${at}.mp3`, durationMs: 1000, voice: "cartesia sonic-3", timed: true, words: [{ text, startMs: 0, endMs: 900 }] }));
    },
    publish: async (name, document) => void published.push({ name, ...document }),
    say: (line) => void said.push(line),
  };
  return { serve, published, said, asked };
}

describe("a tutor before any call", () => {
  it("records every sentence of its macros once and publishes them as walks the page can play", async () => {
    const { serve, published, said, asked } = aServe();
    await Pip.onServe(serve);

    expect(asked).toEqual([["Up here are our services.", "That is all."]]);
    expect(published).toEqual([
      {
        name: "walks",
        walks: [
          {
            name: "tour",
            title: "Site tour",
            when: "the visitor asks to be shown around",
            steps: [
              { say: "Up here are our services.", audio: "https://gw/v1/lines/l0.mp3", durationMs: 1000, words: [{ text: "Up here are our services.", startMs: 0, endMs: 900 }], beats: [{ word: "services.", do: "point", find: ["link", "Services"] }] },
              { say: "That is all.", audio: "https://gw/v1/lines/l1.mp3", durationMs: 1000, words: [{ text: "That is all.", startMs: 0, endMs: 900 }], beats: [] },
            ],
          },
        ],
      },
    ]);
    expect(said).toEqual(["walk tour · 2 sentences · 0:02 · cartesia sonic-3"]);
  });

  it("publishes nothing when it was given no macros", async () => {
    const { serve, published, asked } = aServe();
    await Tutor.onServe(serve);

    expect(asked).toEqual([]);
    expect(published).toEqual([]);
  });

  it("tells the model in its view which walk the visitor played on their own, and how far", async () => {
    const pip = new Pip();
    await runHook(pip, "onEvent", "page.seen", { text: '- link "Services" [ref=e2]', why: "joined" }, META);
    await runHook(pip, "onEvent", "page.walked", { walk: "tour", step: 1, of: 2, done: false }, META);
    expect(pip.seeing()).toContain('your walk "tour", 1 of its 2 sentences on their own');

    await runHook(pip, "onEvent", "page.walked", { walk: "tour", step: 2, of: 2, done: true }, META);
    expect(pip.seeing()).toContain('your walk "tour", all 2 sentences on their own: never give it again unless they ask');
  });
});
