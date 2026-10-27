// A goal button in no form is a spoken call the dot talks on: it presses it and hears the greeting (the agent is heard, not read), says each line into the call for the site to play in, waits for the answer, and goes on with the page once it said goodbye or the call ended.

import { afterEach, describe, expect, it } from "vitest";

import { ReadAloud } from "../../src/tutor/aloud.js";
import { readingOf, SAYING_EVENT, type Reading } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const PAGE = `
  <main data-pinecall-read lang="es">
    <p>Llamala.</p>
    <div class="call">
      <div id="log" data-pinecall-heard></div>
      <button id="call" aria-controls="log" data-pinecall-press="La llamo." data-pinecall-goal="Pedí dos medialunas y despedite.">Llamar</button>
    </div>
    <p>Y seguimos.</p>
  </main>`;

const kinds = (reading: Reading): string[] => reading.walk.steps.map((step) => ("say" in step ? step.say : "press"));

describe("a call the dot talks on", () => {
  it("opens it with its button, hears the greeting, says its lines into it and waits for each answer", async () => {
    document.body.innerHTML = PAGE;
    const log = document.getElementById("log")!;
    const reading = readingOf(document, "Leer")!;
    expect(kinds(reading)).toEqual(["Llamala.", "La llamo.", "press", "Y seguimos."]);

    const pressed: string[] = [];
    const asked: unknown[] = [];
    const told: unknown[] = [];
    let settled = 0;
    const lines = [{ say: "Hola, quiero dos medialunas.", hangup: false }, { say: "Gracias, chau.", hangup: true }];
    log.addEventListener(SAYING_EVENT, (event) => told.push((event as CustomEvent).detail));
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: `https://gw/v1/lines/${text.length}.mp3`, durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      // Pressed, the call opens and the agent greets.
      press: async (element) => {
        pressed.push(element.id);
        log.insertAdjacentHTML("beforeend", `<div data-pinecall-said="agent">La Espiga, ¿qué te sirvo?</div>`);
      },
      // Waited on, the agent has answered what it heard: the line transcribed, a tool used, its words.
      settle: async () => {
        settled += 1;
        if (settled === 1) {
          log.insertAdjacentHTML("beforeend", `<div data-pinecall-said="caller">Hola, quiero dos medialunas.</div><div data-pinecall-said="tool" data-pinecall-say="Acá usó la herramienta anotar Pedido.">⚙</div><div data-pinecall-said="agent">Anotado. ¿Algo más?</div>`);
        }
      },
      next: async (request) => {
        asked.push(request);
        return lines.shift() ?? null;
      },
    });

    // The marker (2): the call opened by its button; the greeting is heard, not read; the first line asked for.
    await aloud.act(2);
    expect(pressed).toEqual(["call"]);
    expect(asked).toEqual([{ goal: "Pedí dos medialunas y despedite.", heard: [{ who: "agent", said: "La Espiga, ¿qué te sirvo?" }], language: "es" }]);
    expect(kinds(reading).slice(3, 5)).toEqual(["Hola, quiero dos medialunas.", "press"]);
    expect(reading.at[3]).toBe(log);
    expect(reading.spoken.get(reading.walk.steps[3]!)).toBe(log);

    // The line shown: the call is told it, with its recording, once.
    await aloud.voice(3);
    aloud.shows(3);
    aloud.shows(3);
    expect(told).toEqual([{ text: "Hola, quiero dos medialunas.", audio: "https://gw/v1/lines/28.mp3", durationMs: 900 }]);

    // The marker again (4): the answer waited on; the tool it used is said, the agent's words are not.
    await aloud.act(4);
    expect(settled).toBe(1);
    expect(kinds(reading).slice(5, 7)).toEqual(["Acá usó la herramienta anotar Pedido.", "press"]);

    // The marker (6): the next line, with all that was said on the call; the dot says goodbye with it.
    await aloud.act(6);
    expect(asked[1]).toEqual({
      goal: "Pedí dos medialunas y despedite.",
      heard: [
        { who: "agent", said: "La Espiga, ¿qué te sirvo?" },
        { who: "caller", said: "Hola, quiero dos medialunas." },
        { who: "agent", said: "Anotado. ¿Algo más?" },
      ],
      language: "es",
    });
    expect(kinds(reading).slice(7, 9)).toEqual(["Gracias, chau.", "press"]);

    // Goodbye said (8): nothing more is asked, and the page goes on.
    await aloud.act(8);
    expect(asked).toHaveLength(2);
    expect(kinds(reading).slice(9)).toEqual(["Y seguimos."]);
  });

  it("ends when the call does: a turn marked end is read, and nothing more is asked", async () => {
    document.body.innerHTML = PAGE;
    const log = document.getElementById("log")!;
    const reading = readingOf(document, "Leer")!;
    const asked: unknown[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      press: async () => {
        log.insertAdjacentHTML("beforeend", `<div data-pinecall-said="end" data-pinecall-say="Cortó el agente: la llamada terminó.">terminó</div>`);
      },
      next: async (request) => {
        asked.push(request);
        return { say: "Hola.", hangup: false };
      },
    });

    await aloud.act(2);
    expect(kinds(reading).slice(3, 5)).toEqual(["Cortó el agente: la llamada terminó.", "press"]);
    await aloud.act(4);

    expect(asked).toEqual([]);
    expect(kinds(reading).slice(5)).toEqual(["Y seguimos."]);
  });
});
