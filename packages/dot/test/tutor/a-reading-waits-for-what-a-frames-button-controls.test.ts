// A reading that presses a button in a frame of the site's own waits for what the button controls on the frame's own page, not the top page's.

import { afterEach, describe, expect, it } from "vitest";

import { Page } from "../../src/page/page.js";
import { Acting } from "../../src/tutor/acting.js";
import { readingWith } from "../../src/tutor/reading.js";

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
});
