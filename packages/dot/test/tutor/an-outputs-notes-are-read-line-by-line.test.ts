// An example's output is read with notes: each finds a line of it, lit and pointed at as it is said; one that finds none is left out, and the output is marked while it is read.

import { afterEach, describe, expect, it } from "vitest";

import { ReadAloud, lineIn, readingOf } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const PAGE = `
  <main data-pinecall-read>
    <p>Corré whoami.</p>
    <button aria-label="Run pinecall whoami" aria-controls="out" data-pinecall-press data-pinecall-notes="notes" data-pinecall-then="Esto es lo que dice.">Run</button>
    <div id="out" data-pinecall-quiet>
      <div class="ln"><span>0,42</span><span>  org <b>lesson</b> · key k_abba · sandbox</span></div>
      <div class="ln"><span>0,42</span><span>  a person's key: the sandbox without --prod</span></div>
    </div>
    <ol id="notes" hidden data-pinecall-skip>
      <li data-pinecall-find="org lesson">Ahí está tu org.</li>
      <li data-pinecall-find="/person's key/i">Y es una key de persona.</li>
      <li data-pinecall-find="production: no">Nunca se dice: no está.</li>
    </ol>
  </main>`;

describe("a line of an output", () => {
  it("is found by a text in any case or a regex, as the innermost box that holds it, never a run of words inside one", () => {
    document.body.innerHTML = PAGE;
    const output = document.getElementById("out")!;
    const lines = [...output.querySelectorAll(".ln")];

    expect(lineIn(output, "ORG lesson")).toBe(lines[0]);
    expect(lineIn(output, "/sandbox without/")).toBe(lines[1]);
    expect(lineIn(output, "nowhere")).toBeNull();
    expect(lineIn(output, "/[/")).toBeNull();
  });
});

describe("an output read with notes", () => {
  it("says what it shows, then each note pointing at its line, and marks the output while it does", async () => {
    document.body.innerHTML = PAGE;
    const reading = readingOf(document, "Leer")!;
    expect(reading.walk.steps.map((step) => ("say" in step ? step.say : "press"))).toEqual([
      "Corré whoami.", "press", "Esto es lo que dice.", "Ahí está tu org.", "Y es una key de persona.", "Nunca se dice: no está.",
    ]);
    const output = document.getElementById("out")!;
    expect(reading.outputs.map((about) => about?.find)).toEqual([undefined, undefined, null, "org lesson", "/person's key/i", "production: no"]);

    const lit: (string | null)[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: (element) => void lit.push(element === null ? null : (element.textContent ?? "").replace(/\s+/g, " ").trim()),
      press: async () => undefined,
    });
    aloud.shows(0);
    expect(output.hasAttribute("data-pinecall-reading")).toBe(false);
    aloud.shows(2);
    expect(output.hasAttribute("data-pinecall-reading")).toBe(true);
    aloud.shows(3);
    aloud.shows(4);
    // The note with no line is skipped as it is reached, not recorded.
    expect(await aloud.voice(5)).toBeNull();
    expect((await aloud.voice(3))?.say).toBe("Ahí está tu org.");
    aloud.shows(-1);

    expect(lit.map((text) => text && text.slice(0, 22))).toEqual(["Corré whoami.", "0,42 org lesson · key ", "0,42 org lesson · key ", "0,42 a person's key: t", null]);
    expect(output.hasAttribute("data-pinecall-reading")).toBe(false);
  });
});

describe("an output with no notes of the page's", () => {
  it("is explained by the site's door once the example answered, its notes read as the page's would be", async () => {
    document.body.innerHTML = `
      <main data-pinecall-read>
        <button aria-label="Run npm install" aria-controls="out" data-pinecall-press data-pinecall-explain="npm install" data-pinecall-then="Listo.">Run</button>
        <div id="out" data-pinecall-quiet><div class="ln"><span>1,08</span><span>up to date, audited 49 packages</span></div><div class="ln"><span>1,09</span><span>found 0 vulnerabilities</span></div></div>
        <p>Y seguimos.</p>
      </main>`;
    const reading = readingOf(document, "Leer")!;
    const asked: unknown[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      press: async () => undefined,
      explain: async (request) => {
        asked.push(request);
        return [{ find: "audited 49 packages", say: "Revisó cuarenta y nueve paquetes." }, { find: "0 vulnerabilities", say: "Y no encontró vulnerabilidades." }];
      },
    });

    await aloud.act(0);

    expect(asked).toEqual([{ output: "1,08 up to date, audited 49 packages\n1,09 found 0 vulnerabilities", command: "npm install", language: undefined }]);
    expect(reading.walk.steps.map((step) => ("say" in step ? step.say : "press"))).toEqual([
      "press", "Listo.", "Revisó cuarenta y nueve paquetes.", "Y no encontró vulnerabilidades.", "Y seguimos.",
    ]);
    expect(reading.outputs.map((about) => about?.find)).toEqual([undefined, null, "audited 49 packages", "0 vulnerabilities", undefined]);
    expect((await aloud.voice(2))?.say).toBe("Revisó cuarenta y nueve paquetes.");
  });
});
