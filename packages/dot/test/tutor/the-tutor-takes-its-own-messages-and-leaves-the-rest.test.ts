// The tutor puts one layer on the page, takes the cursor moves and macro steps meant for it and leaves cards to the page, and leaves nothing behind.

import { afterEach, describe, expect, it } from "vitest";

import { tutor } from "../../src/tutor/tutor.js";
import { aRoom } from "../a-room.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

describe("the tutor on a page", () => {
  it("puts its person on the page, out of what the agent reads, with its face as a button", () => {
    const one = tutor(aRoom(), { label: "Talk to Pip" });

    const layer = document.querySelector("[data-pinecall-skip]");
    expect(layer).not.toBeNull();
    expect(layer?.querySelector('[role="button"]')?.getAttribute("aria-label")).toBe("Talk to Pip");
    expect(layer?.querySelector("svg")).not.toBeNull();
    one.close();
  });

  it("takes a cursor move and a macro step, and leaves a card or choices to the page", () => {
    const one = tutor(aRoom());

    expect(one.take({ type: "cursor", action: "home" })).toBe(true);
    expect(one.take({ type: "macro.step", macro: "tour", step: 0, say: "Hi.", beats: [] })).toBe(true);
    expect(one.take({ type: "choices", options: [{ label: "Tuesday" }] })).toBe(false);
    one.close();
  });

  it("calls the page back when its face is clicked", () => {
    let clicks = 0;
    const one = tutor(aRoom(), { onClick: () => (clicks += 1) });
    document.querySelector<HTMLElement>('[data-pinecall-skip] [role="button"]')?.click();

    expect(clicks).toBe(1);
    one.close();
  });

  it("leaves the page as it found it when closed, twice or not", () => {
    const one = tutor(aRoom());
    one.close();
    one.close();

    expect(document.querySelector("[data-pinecall-skip]")).toBeNull();
    expect(document.head.querySelectorAll("style")).toHaveLength(0);
  });
});
