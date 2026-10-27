// A reading that presses a button in a frame of the site's own waits for what the button controls on the frame's own page, not the top page's; the wait holds no move of the pointer's.

import { afterEach, describe, expect, it } from "vitest";

import { Page } from "../../src/page/page.js";
import { Acting } from "../../src/tutor/acting.js";
import { readingWith } from "../../src/tutor/aloud.js";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("a reading's press in a frame", () => {
  it("resolves once the frame's output answered, as a press on the page does", async () => {
    document.body.innerHTML = `<main data-pinecall-read><iframe id="f"></iframe></main>`;
    await new Promise((done) => setTimeout(done, 50));
    const page = (document.getElementById("f") as HTMLIFrameElement).contentDocument!;
    page.body.innerHTML = `<div id="log"></div><form><input id="t"><button id="send" type="button" aria-controls="log">Enviar</button></form>`;
    const log = page.getElementById("log")!;
    page.getElementById("send")!.addEventListener("click", () => setTimeout(() => log.insertAdjacentHTML("beforeend", `<div data-pinecall-said="agent">Hola.</div>`), 50));
    const acting = new Acting({ document, page: new Page(document), queued: (work) => work(), point: async () => undefined, ring: () => undefined, type: async () => null });
    const options = readingWith("Leer", acting, { light: () => undefined, queued: (work) => work() });

    await options.press(page.getElementById("send")!);

    expect(log.textContent).toBe("Hola.");
  });

  it("holds no move while it waits: a move queued after the press runs before the output answers", async () => {
    document.body.innerHTML = `<main data-pinecall-read><div id="log"></div><form><button id="send" type="button" aria-controls="log">Enviar</button></form></main>`;
    const log = document.getElementById("log")!;
    document.getElementById("send")!.addEventListener("click", () => setTimeout(() => log.insertAdjacentHTML("beforeend", `<div>Hola.</div>`), 400));
    // The pointer's queue: one move after another.
    let last: Promise<unknown> = Promise.resolve();
    const queued = <T,>(work: () => Promise<T>): Promise<T> => {
      const next = last.then(work);
      last = next.catch(() => undefined);
      return next;
    };
    const acting = new Acting({ document, page: new Page(document), queued, point: async () => undefined, ring: () => undefined, type: async () => null });
    const options = readingWith("Leer", acting, { light: () => undefined, queued });
    const order: string[] = [];

    const pressed = options.press(document.getElementById("send")!).then(() => order.push("answered"));
    await queued(async () => void order.push("moved"));
    await pressed;

    expect(order).toEqual(["moved", "answered"]);
  });
});
