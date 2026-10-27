// A send button marked with a goal is a chat the dot talks to: it asks the door for its line, says it, types and sends it, reads the agent's answer aloud, and when it has said goodbye has the whole chat explained.

import { afterEach, describe, expect, it } from "vitest";

import { ReadAloud } from "../../src/tutor/aloud.js";
import { readingOf, type Reading } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const PAGE = `
  <main data-pinecall-read lang="es">
    <p>Hablale.</p>
    <div class="chat">
      <div id="log"></div>
      <form><input id="t" placeholder="Escribí…"><button id="send" aria-controls="log" data-pinecall-press="Le escribo yo." data-pinecall-goal="Pedí dos medialunas y despedite." data-pinecall-explain="La conversación entera.">Enviar</button></form>
    </div>
    <p>Y seguimos.</p>
  </main>`;

const kinds = (reading: Reading): string[] => reading.walk.steps.map((step) => ("say" in step ? step.say : "fill" in step ? `fill:${step.with}` : "press"));

describe("a chat the dot talks to", () => {
  it("is a turn at a time: the line typed as it is said, sent, the answer read aloud, and the whole chat explained at the end", async () => {
    document.body.innerHTML = PAGE;
    document.documentElement.lang = "es";
    const log = document.getElementById("log")!;
    const reading = readingOf(document, "Leer")!;
    expect(kinds(reading)).toEqual(["Hablale.", "Le escribo yo.", "press", "Y seguimos."]);
    // Its opening line is said pointing at the chat, not at its button.
    expect(reading.at[1]?.id).toBe("log");

    const asked: unknown[] = [];
    const typed: string[] = [];
    const explained: unknown[] = [];
    const lines = [{ say: "Hola, quiero dos medialunas.", hangup: false }, { say: "Gracias, chau.", hangup: true }];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      type: async (_element, text) => void typed.push(text),
      press: async () => {
        // The chat answers the line typed last.
        const said = typed.at(-1) ?? "";
        log.insertAdjacentHTML("beforeend", `<div data-pinecall-said="caller">${said}</div><div data-pinecall-said="agent">${said.includes("chau") ? "Hasta luego." : "Dos medialunas, anotado. ¿Algo más?"}</div>`);
      },
      next: async (request) => {
        asked.push(request);
        return lines.shift() ?? null;
      },
      explain: async (request) => {
        explained.push(request);
        return [{ find: "anotado", say: "Lo anotó." }];
      },
    });
    /** The `at`th line said: recorded, shown (its typing started), as the walker does. */
    const said = async (at: number): Promise<void> => {
      await aloud.voice(at);
      aloud.shows(at);
    };

    // The marker (step 2): the first line asked for, said and typed meanwhile, sent, and the turn after that marked.
    await aloud.act(2);
    expect(asked).toEqual([{ goal: "Pedí dos medialunas y despedite.", heard: [], language: "es" }]);
    expect(kinds(reading).slice(3, 7)).toEqual(["Hola, quiero dos medialunas.", "press", "press", "Y seguimos."]);
    expect(reading.at[3]?.id).toBe("t");
    expect(reading.at[4]?.id).toBe("send");
    await said(3);
    expect(typed).toEqual(["Hola, quiero dos medialunas."]);
    await aloud.act(4);
    expect(explained).toEqual([]);

    // The marker again (5): the agent's answer read aloud, pointing at it, then the next turn marked.
    await aloud.act(5);
    expect(kinds(reading).slice(6, 8)).toEqual(["Dos medialunas, anotado. ¿Algo más?", "press"]);
    expect(reading.at[6]?.getAttribute("data-pinecall-said")).toBe("agent");

    // The next line (7), with the chat so far; the dot says goodbye with it.
    await aloud.act(7);
    expect(asked[1]).toEqual({
      goal: "Pedí dos medialunas y despedite.",
      heard: [{ who: "caller", said: "Hola, quiero dos medialunas." }, { who: "agent", said: "Dos medialunas, anotado. ¿Algo más?" }],
      language: "es",
    });
    expect(kinds(reading).slice(8, 11)).toEqual(["Gracias, chau.", "press", "press"]);
    await said(8);
    await aloud.act(9);
    await aloud.act(10); // the agent's last answer read aloud
    expect(kinds(reading).slice(11, 13)).toEqual(["Hasta luego.", "press"]);

    // Goodbye said (12): the talk is over and the whole chat explained, then the page goes on.
    await aloud.act(12);
    expect(asked).toHaveLength(2);
    expect(explained).toEqual([{ output: "Hola, quiero dos medialunas.\nDos medialunas, anotado. ¿Algo más?\nGracias, chau.\nHasta luego.", command: "La conversación entera.", language: "es" }]);
    expect(kinds(reading).slice(13)).toEqual(["Lo anotó.", "Y seguimos."]);
  });

  it("ends when the chat does: a send button disabled is a call that was hung up", async () => {
    document.body.innerHTML = PAGE;
    const reading = readingOf(document, "Leer")!;
    (document.getElementById("send") as HTMLButtonElement).disabled = true;
    const asked: unknown[] = [];
    const aloud = new ReadAloud(reading, {
      record: async (text) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] }),
      light: () => undefined,
      press: async () => undefined,
      next: async (request) => {
        asked.push(request);
        return { say: "Hola.", hangup: false };
      },
      explain: async () => [],
    });

    await aloud.act(2);

    expect(asked).toEqual([]);
    expect(kinds(reading)).toEqual(["Hablale.", "Le escribo yo.", "press", "Y seguimos."]);
  });
});
