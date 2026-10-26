// A page is read aloud with no call: what it marks to read, part by part as written, an example pressed on the way, each part recorded as it is reached and the next one asked for while one plays.

import { afterEach, describe, expect, it } from "vitest";

import { recordRead } from "../../src/server/saying.js";
import { ReadAloud, piecesOf, readingOf } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const PAGE = `
  <nav><p>Not read: outside what is marked.</p></nav>
  <main data-pinecall-read>
    <h2>Cómo leer esto</h2>
    <p>Cada comando está en un bloque con <strong>Run</strong>.</p>
    <ul><li><p>Un ítem, leído una vez.</p></li></ul>
    <div class="card"><h4>panaderia</h4><p>El proyecto del agente.</p></div>
    <div class="blk" data-pinecall-quiet>
      <p>pinecall whoami</p>
      <button aria-label="Run pinecall whoami" aria-controls="out-1" data-pinecall-press="Lo corro.">▶ Run</button>
    </div>
    <p hidden>Hidden.</p>
    <p>Lo que imprimió es tu org.</p>
  </main>`;

describe("a page read aloud", () => {
  it("is what it marks, in the page's order, each part once, a card with its title, an example pressed with its sentence first", () => {
    document.body.innerHTML = PAGE;
    const reading = readingOf(document, "Leer el capítulo");

    expect(reading?.walk.title).toBe("Leer el capítulo");
    expect(reading?.walk.steps).toEqual([
      { say: "Cómo leer esto", beats: [], live: true },
      { say: "Cada comando está en un bloque con Run.", beats: [], live: true },
      { say: "Un ítem, leído una vez.", beats: [], live: true },
      { say: "panaderia. El proyecto del agente.", beats: [], live: true },
      { say: "Lo corro.", beats: [], live: true },
      { press: "Run pinecall whoami" },
      { say: "Lo que imprimió es tu org.", beats: [], live: true },
    ]);
    // A card is read whole, title and words, and lit whole.
    expect(reading?.at.map((element) => element.tagName.toLowerCase())).toEqual(["h2", "p", "li", "div", "button", "button", "p"]);
    document.body.innerHTML = "<main><p>Nothing marked.</p></main>";
    expect(readingOf(document, "x")).toBeNull();
  });

  it("reads a long part a few sentences at a time, a sentence longer than one cut between its words", () => {
    expect(piecesOf("Uno. Dos. Tres.", 10)).toEqual(["Uno. Dos.", "Tres."]);
    expect(piecesOf("una palabra tras otra", 12)).toEqual(["una palabra", "tras otra"]);
    expect(piecesOf("", 10)).toEqual([]);
  });

  it("records each part as it is reached, the next one asked for at once, and lights the part read", async () => {
    document.body.innerHTML = PAGE;
    const reading = readingOf(document, "Leer");
    if (reading === null) throw new Error("no reading");
    const recorded: string[] = [];
    const lit: (string | null)[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => {
        recorded.push(text);
        return { say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] };
      },
      light: (element) => void lit.push(element?.tagName.toLowerCase() ?? null),
      press: async () => undefined,
    });

    expect((await aloud.voice(0))?.say).toBe("Cómo leer esto");
    expect(recorded).toEqual(["Cómo leer esto", "Cada comando está en un bloque con Run."]);
    await aloud.voice(1);
    expect(recorded).toHaveLength(3);
    // The press is no sentence: the one after it is asked for.
    await aloud.voice(4);
    expect(recorded.at(-1)).toBe("Lo que imprimió es tu org.");

    aloud.shows(1);
    await aloud.act(5);
    aloud.shows(-1);
    expect(lit).toEqual(["p", "button", null]);
  });
});

describe("a page's text recorded on the site's server", () => {
  it("is refused unless the site lets its pages be read, and is a line of 480 characters at most", async () => {
    const lines = async () => new Response(JSON.stringify({ lines: [{ url: "https://gw/v1/lines/r.mp3", duration_ms: 700, words: [] }] }));
    await expect(recordRead("Hola.", { key: "k", agent: "guia" }, lines)).rejects.toThrow("reads no page aloud");
    expect(await recordRead("  Hola,\n mundo. ", { key: "k", agent: "guia", read: true }, lines)).toEqual({ say: "Hola, mundo.", audio: "https://gw/v1/lines/r.mp3", durationMs: 700, words: [] });
    await expect(recordRead("x".repeat(481), { key: "k", agent: "guia", read: true }, lines)).rejects.toThrow("1 to 480");
  });
});
