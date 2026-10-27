// A page read aloud reaches into a frame of the site's own: what its page marks is read in the frame's place, a field typed with the page's own example, the button after it pressed in its form, and the answer explained.

import { afterEach, describe, expect, it } from "vitest";

import { ReadAloud, readingOf } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("a page read aloud", () => {
  it("types the page's example into a frame's field, sends it with the button after it, and has the answer explained", async () => {
    document.body.innerHTML = `<main data-pinecall-read><p>Preguntale.</p><iframe id="f"></iframe><p>No lo sabe.</p></main>`;
    await new Promise((done) => setTimeout(done, 50));
    const page = (document.getElementById("f") as HTMLIFrameElement).contentDocument!;
    page.documentElement.lang = "es";
    page.body.innerHTML = `
      <div id="log"><div data-pinecall-skip>Escribile como un cliente.</div></div>
      <form data-pinecall-read>
        <input id="t" placeholder="Escribí…" data-pinecall-type="¿A qué hora abren?">
        <button id="send" aria-controls="log" data-pinecall-press="Le pregunto." data-pinecall-explain="Le preguntaste: ¿A qué hora abren?">Enviar</button>
      </form>`;
    const reading = readingOf(document, "Leer")!;

    expect(reading.walk.steps).toEqual([
      { say: "Preguntale.", beats: [], live: true },
      { fill: "Escribí…", with: "¿A qué hora abren?" },
      { say: "Le pregunto.", beats: [], live: true },
      { press: "Enviar" },
      { say: "No lo sabe.", beats: [], live: true },
    ]);
    expect(reading.at[1]).toBe(page.getElementById("t"));
    expect(reading.at[3]).toBe(page.getElementById("send"));

    const typed: string[] = [];
    const pressed: Element[] = [];
    const asked: unknown[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      type: async (_element, text) => void typed.push(text),
      press: async (element) => {
        pressed.push(element);
        page.getElementById("log")!.insertAdjacentHTML("beforeend", `<div data-pinecall-said="caller">¿A qué hora abren?</div><div data-pinecall-said="agent">Abrimos a las nueve.</div>`);
      },
      explain: async (request) => {
        asked.push(request);
        return [{ find: "a las nueve", say: "Dice que abre a las nueve: lo inventó." }];
      },
    });

    await aloud.act(1);
    expect(typed).toEqual(["¿A qué hora abren?"]);

    await aloud.act(3);
    expect(pressed).toEqual([page.getElementById("send")]);
    expect(asked).toEqual([{ output: "¿A qué hora abren?\nAbrimos a las nueve.", command: "Le preguntaste: ¿A qué hora abren?", language: "es" }]);
    // The answer is read as it came, pointing at it, then what the model says of it.
    expect(reading.walk.steps.map((step) => ("say" in step ? step.say : "fill" in step ? "fill" : "press"))).toEqual([
      "Preguntale.", "fill", "Le pregunto.", "press", "Abrimos a las nueve.", "Dice que abre a las nueve: lo inventó.", "No lo sabe.",
    ]);
    expect(reading.at[4]?.getAttribute("data-pinecall-said")).toBe("agent");
  });
});
