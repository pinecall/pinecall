// A frame of the site's own: its page is found, a page's frame is found (by its page when the window does not say), and an element in it stands where the frame does on the top page.

import { afterEach, describe, expect, it } from "vitest";

import { boxOf, frameOf, framesIn, isElement, onTop, originOf, pageOf } from "../../src/pointer/frames.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const rect = (left: number, top: number, width: number, height: number): DOMRect =>
  ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect;

/** A frame on the page, its page loaded with `html`, standing at (`left`, `top`) on the screen. */
async function framed(html: string, left: number, top: number): Promise<{ frame: HTMLIFrameElement; page: Document }> {
  document.body.innerHTML = `<main><p>antes</p><iframe id="f"></iframe></main>`;
  await new Promise((done) => setTimeout(done, 50));
  const frame = document.getElementById("f") as HTMLIFrameElement;
  const page = frame.contentDocument!;
  page.body.innerHTML = html;
  frame.getBoundingClientRect = () => rect(left, top, 400, 300);
  return { frame, page };
}

describe("a frame of the site's own", () => {
  it("shows a page the pointer reaches, and is found from that page", async () => {
    const { frame, page } = await framed(`<button id="b">Enviar</button>`, 100, 200);

    expect(pageOf(frame)).toBe(page);
    expect(frameOf(page)).toBe(frame);
    expect(frameOf(document)).toBeNull();
    expect(framesIn(document)).toEqual([page]);
    expect(isElement(page.getElementById("b"))).toBe(true);
    expect(isElement(page.createTextNode("x"))).toBe(false);
  });

  it("moves an element's box by where the frame stands on the top page", async () => {
    const { page } = await framed(`<button id="b">Enviar</button>`, 100, 200);
    const button = page.getElementById("b")!;
    button.getBoundingClientRect = () => rect(10, 20, 80, 30);

    expect(originOf(page)).toEqual({ x: 100, y: 200 });
    expect(boxOf(button)).toEqual({ left: 110, top: 220, right: 190, bottom: 250, width: 80, height: 30 });
    expect(onTop(rect(0, 0, 400, 300), document)).toEqual({ left: 0, top: 0, right: 400, bottom: 300, width: 400, height: 300 });
  });
});
