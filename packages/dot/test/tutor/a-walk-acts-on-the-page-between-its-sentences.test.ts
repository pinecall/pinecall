// A walk called with values acts on the page between its sentences: it fills, presses, waits and reads, records a sentence with slots when it reaches it, and leaves out a step nothing filled.

import { afterEach, describe, expect, it, vi } from "vitest";

import { Page } from "../../src/page/page.js";
import { Acting } from "../../src/tutor/acting.js";
import { Walking, type WalkHooks } from "../../src/tutor/walking.js";
import type { RecordedStep, RecordedWalk } from "../../src/wire/index.js";

const said = (say: string, audio: string): RecordedStep => ({ say, audio, durationMs: 1000, words: [{ text: say, startMs: 0, endMs: 900 }], beats: [] });

const FIND: RecordedWalk = {
  name: "find",
  title: "Find a time",
  params: { treatment: { about: "what they want done" } },
  steps: [
    said("Let me look.", "https://gw/v1/lines/a.mp3"),
    { fill: "Treatment", with: "{treatment}" },
    { read: "Open times", as: "hit" },
    { say: "The soonest is {hit.Day}.", beats: [{ word: "soonest", do: "highlight", find: ["row", "{hit}"] }], live: true, if: "hit" },
    { say: "Nothing for {treatment}.", beats: [], live: true, unless: "hit" },
  ],
};

function anAudio(): HTMLAudioElement {
  const audio = document.createElement("audio");
  vi.spyOn(audio, "play").mockResolvedValue(undefined);
  vi.spyOn(audio, "pause").mockReturnValue(undefined);
  return audio;
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("a walk with acts", () => {
  it("plays a sentence, does its acts in turn with the values, and records the sentence the row it read fills", async () => {
    const audio = anAudio();
    const done: string[] = [];
    const hooks: WalkHooks = {
      act: async (step, values) => {
        done.push(`act ${JSON.stringify(step)} ${JSON.stringify(values)}`);
        return "read" in step ? { hit: "Tue · 9:00", "hit.Day": "Tue" } : {};
      },
      // As the door records it: the sentence filled, the step's own beats.
      voice: async (walk, at, values) => {
        done.push(`voice ${at} ${values["hit.Day"] ?? "-"}`);
        const step = walk.steps[at];
        return { ...said(`The soonest is ${values["hit.Day"] ?? ""}.`, "https://gw/v1/lines/live.mp3"), beats: step !== undefined && "beats" in step ? step.beats : [] };
      },
    };
    const ended: string[] = [];
    const walking = new Walking(audio, (walked) => ended.push(`${walked.walk} ${walked.done}`), () => undefined, hooks);

    walking.start(FIND, { treatment: "cleaning" });
    expect(audio.src).toBe("https://gw/v1/lines/a.mp3");
    audio.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(audio.src).toBe("https://gw/v1/lines/live.mp3"));

    expect(done).toEqual([
      'act {"fill":"Treatment","with":"{treatment}"} {"treatment":"cleaning"}',
      'act {"read":"Open times","as":"hit"} {"treatment":"cleaning"}',
      "voice 3 Tue",
    ]);
    // The beat's slot is filled with the row it read, for the pointer to find it.
    audio.currentTime = 0.1;
    expect(walking.frame()?.beats).toEqual([{ word: "soonest", do: "highlight", find: ["row", "Tue · 9:00"] }]);
    // The step for no row is left out: the walk ends after the row's sentence.
    audio.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(ended).toEqual(["find true"]));
  });

  it("is quiet between two sentences, while an act is done", async () => {
    const walking = new Walking(anAudio(), () => undefined, () => undefined, { act: () => new Promise(() => undefined), voice: async () => null });
    walking.start({ name: "w", title: "W", steps: [{ press: "Search" }] });
    await Promise.resolve();
    expect(walking.frame()).toEqual({ lit: "", coming: "", beats: [], fraction: 0 });
  });
});

describe("the acts on the page", () => {
  function anActing(door?: (request: unknown) => Promise<unknown>): { acting: Acting; moves: string[] } {
    document.body.innerHTML = `
      <form role="search" aria-label="Find a time"><label for="q">Treatment<input id="q"></label><button type="submit">Search times</button></form>
      <table><caption>Open times</caption><thead><tr><th>Day</th><th>Time</th><th>Dentist</th></tr></thead>
      <tbody><tr><td>Tue, Oct 28</td><td>9:00</td><td>Dr. Patel</td></tr><tr><td>Wed, Oct 29</td><td>17:30</td><td>Dr. Okafor</td></tr></tbody></table>`;
    // The site's own search answers on the page: it never leaves it.
    document.querySelector("form")?.addEventListener("submit", (event) => event.preventDefault());
    const moves: string[] = [];
    const acting = new Acting({
      document,
      page: new Page(document),
      queued: (work) => work(),
      point: async (element) => void moves.push(`point ${element.tagName.toLowerCase()}`),
      ring: () => void moves.push("ring"),
      type: async (element, text) => {
        moves.push(`type ${element.id} ${text}`);
        return null;
      },
      door,
    });
    return { acting, moves };
  }

  it("fills a field the site names with the visitor's words, and presses its search with the pointer on it", async () => {
    const { acting, moves } = anActing();
    await acting.act({ fill: "Treatment", with: "{treatment}" }, { treatment: "cleaning" }, "");
    await acting.act({ press: "Search times" }, {}, "");
    expect(moves).toEqual(["type q cleaning", "point button", "ring"]);
  });

  it("reads a table by its header's words: the first row, or the one the site's door picks for what was typed", async () => {
    const first = await anActing().acting.act({ read: "Open times", as: "hit" }, {}, "");
    expect(first).toEqual({ hit: "Tue, Oct 28 · 9:00 · Dr. Patel", "hit.Day": "Tue, Oct 28", "hit.Time": "9:00", "hit.Dentist": "Dr. Patel" });

    const asked: unknown[] = [];
    const { acting } = anActing(async (request) => {
      asked.push(request);
      return { row: 1 };
    });
    expect(await acting.act({ read: "Open times", as: "hit", row: "best" }, {}, "after work")).toMatchObject({ "hit.Time": "17:30" });
    expect(asked).toEqual([{ row: { message: "after work", rows: ["Tue, Oct 28 · 9:00 · Dr. Patel", "Wed, Oct 29 · 17:30 · Dr. Okafor"] } }]);
  });

  it("waits for what it waits on to change after a press, stay still and not be busy, or for its time", async () => {
    const { acting } = anActing();
    const button = document.querySelector("button") ?? document.body;
    const table = document.querySelector("table") ?? document.body;
    await acting.press(button);
    const started = performance.now();
    const waiting = acting.wait(() => table, 3000);
    // The site's search says it is busy while it asks, as a search should.
    table.setAttribute("aria-busy", "true");
    document.querySelector("tbody")?.append(document.createElement("tr"));
    setTimeout(() => table.setAttribute("aria-busy", "false"), 500);
    expect(await waiting).toBe(true);
    expect(performance.now() - started).toBeGreaterThanOrEqual(500);

    // A change elsewhere on the page is not the search answered.
    const elsewhere = acting.wait(() => table, 400);
    document.body.append(document.createElement("p"));
    expect(await elsewhere).toBe(false);
  });
});

describe("a walk skipped", () => {
  it("goes on to the next sentence, doing an act on the way, and back to the one before, passing an act over", async () => {
    const audio = anAudio();
    const acted: string[] = [];
    const walk: RecordedWalk = {
      name: "w",
      title: "W",
      steps: [said("One.", "https://gw/v1/lines/1.mp3"), { press: "Search" }, said("Two.", "https://gw/v1/lines/2.mp3"), said("Three.", "https://gw/v1/lines/3.mp3")],
    };
    const walking = new Walking(audio, () => undefined, () => undefined, {
      act: async (step) => {
        acted.push(JSON.stringify(step));
        return {};
      },
      voice: async () => null,
    });
    walking.start(walk);

    walking.skip(1);
    await vi.waitFor(() => expect(audio.src).toBe("https://gw/v1/lines/2.mp3"));
    expect(acted).toEqual(['{"press":"Search"}']);
    walking.skip(-1);
    await vi.waitFor(() => expect(audio.src).toBe("https://gw/v1/lines/1.mp3"));
    walking.skip(1);
    await vi.waitFor(() => expect(audio.src).toBe("https://gw/v1/lines/2.mp3"));
    expect(acted).toHaveLength(2);
  });
});
