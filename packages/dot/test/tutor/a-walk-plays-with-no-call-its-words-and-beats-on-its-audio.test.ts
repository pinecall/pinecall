// A recorded walk plays with no call: one audio element through its sentences, the words lit and the beats run as its audio reaches them.

import { afterEach, describe, expect, it, vi } from "vitest";

import { Walking, lengthOf, publishedWalks, type Walked } from "../../src/tutor/walking.js";
import type { RecordedWalk } from "../../src/wire/index.js";

const WALK: RecordedWalk = {
  name: "tour",
  title: "Site tour",
  steps: [
    {
      say: "Up here are our services.",
      audio: "https://gw/v1/lines/a.mp3",
      durationMs: 2000,
      words: [
        { text: "Up", startMs: 0, endMs: 300 },
        { text: "here", startMs: 300, endMs: 600 },
        { text: "are", startMs: 600, endMs: 800 },
        { text: "our", startMs: 800, endMs: 1000 },
        { text: "services.", startMs: 1000, endMs: 1800 },
      ],
      beats: [{ word: "services.", do: "point", find: ["link", "Services"] }],
    },
    { say: "That is all.", audio: "https://gw/v1/lines/b.mp3", durationMs: 1000, words: [{ text: "That", startMs: 0, endMs: 200 }], beats: [] },
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
});

describe("a walk played", () => {
  it("plays its first sentence from CORS, lights the words its audio has reached, and runs a beat on its word", () => {
    const audio = anAudio();
    const walking = new Walking(audio, () => undefined);
    walking.start(WALK);

    expect(audio.crossOrigin).toBe("anonymous");
    expect(audio.src).toBe("https://gw/v1/lines/a.mp3");
    audio.currentTime = 0.65;
    const early = walking.frame();
    expect(early?.lit).toBe("Up here are");
    expect(early?.coming).toBe(" our services.");
    expect(early?.beats).toEqual([]);
    expect(early?.fraction).toBeCloseTo(650 / 3000, 3);

    audio.currentTime = 1.1;
    expect(walking.frame()?.beats).toEqual([{ word: "services.", do: "point", find: ["link", "Services"] }]);
    expect(walking.frame()?.beats).toEqual([]);
  });

  it("goes on to the next sentence on the same element, and says it ended when the last one did", () => {
    const audio = anAudio();
    const ended: Walked[] = [];
    const walking = new Walking(audio, (walked) => ended.push(walked));
    walking.start(WALK);
    audio.dispatchEvent(new Event("ended"));

    expect(audio.src).toBe("https://gw/v1/lines/b.mp3");
    audio.dispatchEvent(new Event("ended"));
    expect(ended).toEqual([{ walk: "tour", step: 2, of: 2, done: true }]);
    expect(walking.playing).toBeNull();
  });

  it("stops where it is, saying how far the visitor got, and plays nothing after", () => {
    const audio = anAudio();
    const walking = new Walking(audio, () => undefined);
    walking.start(WALK);

    expect(walking.stop()).toEqual({ walk: "tour", step: 1, of: 2, done: false });
    expect(walking.frame()).toBeNull();
    expect(walking.stop()).toBeNull();
  });

  it("says what each sentence shows as it starts, and that nothing shows once it stops", () => {
    const audio = anAudio();
    const shown: (string | null)[] = [];
    const walking = new Walking(audio, () => undefined, (step) => shown.push(step?.say ?? null));
    walking.start(WALK);
    audio.dispatchEvent(new Event("ended"));
    walking.stop();

    expect(shown).toEqual(["Up here are our services.", "That is all.", null]);
  });

  it("is as long as its sentences", () => {
    expect(lengthOf(WALK)).toBe(3000);
  });
});

describe("the walks an agent published", () => {
  it("are read with no key, none where the page cannot read them, and none asked for none", async () => {
    const fetching = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ walks: [WALK] })));

    expect(await publishedWalks("https://gw/v1/agents/pip/public/walks")).toEqual([WALK]);
    fetching.mockResolvedValueOnce(new Response("no", { status: 404 }));
    expect(await publishedWalks("https://gw/v1/agents/pip/public/walks")).toEqual([]);
    expect(await publishedWalks("")).toEqual([]);
    expect(fetching).toHaveBeenCalledTimes(2);
  });
});
