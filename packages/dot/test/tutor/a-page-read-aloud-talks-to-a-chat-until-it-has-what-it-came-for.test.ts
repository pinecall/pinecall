// A send button marked with a goal is a chat the dot talks to: it asks the door for its line, says it, types and sends it, reads the agent's answer aloud, and when it has said goodbye has the whole chat explained.

import { afterEach, describe, expect, it } from "vitest";

import { ReadAloud, readingOf, type Reading } from "../../src/tutor/reading.js";

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
  it("is a turn at a time: the line said and typed, sent, the answer read aloud, and the whole chat explained at the end", async () => {
    document.body.innerHTML = PAGE;
    document.documentElement.lang = "es";
    const log = document.getElementById("log")!;
    const reading = readingOf(document, "Leer")!;
    expect(kinds(reading)).toEqual(["Hablale.", "Le escribo yo.", "press", "Y seguimos."]);

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

    // The marker (step 2): the first line asked for, then said, typed and sent after it, and the turn after that marked.
    await aloud.act(2);
    expect(asked).toEqual([{ goal: "Pedí dos medialunas y despedite.", heard: [], language: "es" }]);
    expect(kinds(reading).slice(3, 8)).toEqual(["Hola, quiero dos medialunas.", "fill:Hola, quiero dos medialunas.", "press", "press", "Y seguimos."]);
    expect(reading.at[3]?.id).toBe("t");
    expect(reading.at[5]?.id).toBe("send");
    await aloud.act(4);
    await aloud.act(5);
    expect(typed).toEqual(["Hola, quiero dos medialunas."]);
    expect(explained).toEqual([]);

    // The marker again (6): the agent's answer read aloud, pointing at it, then the next turn marked.
    await aloud.act(6);
    expect(kinds(reading).slice(7, 9)).toEqual(["Dos medialunas, anotado. ¿Algo más?", "press"]);
    expect(reading.at[7]?.getAttribute("data-pinecall-said")).toBe("agent");

    // The next line (8), with the chat so far; the dot says goodbye with it.
    await aloud.act(8);
    expect(asked[1]).toEqual({
      goal: "Pedí dos medialunas y despedite.",
      heard: [{ who: "caller", said: "Hola, quiero dos medialunas." }, { who: "agent", said: "Dos medialunas, anotado. ¿Algo más?" }],
      language: "es",
    });
    expect(kinds(reading).slice(9, 13)).toEqual(["Gracias, chau.", "fill:Gracias, chau.", "press", "press"]);
    await aloud.act(10);
    await aloud.act(11);
    await aloud.act(12); // the agent's last answer read aloud
    expect(kinds(reading).slice(13, 15)).toEqual(["Hasta luego.", "press"]);

    // Goodbye said (14): the talk is over and the whole chat explained, then the page goes on.
    await aloud.act(14);
    expect(asked).toHaveLength(2);
    expect(explained).toEqual([{ output: "Hola, quiero dos medialunas.\nDos medialunas, anotado. ¿Algo más?\nGracias, chau.\nHasta luego.", command: "La conversación entera.", language: "es" }]);
    expect(kinds(reading).slice(15)).toEqual(["Lo anotó.", "Y seguimos."]);
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
