// The pointer presses a button a walk names: one outside any form, or in a search form; never a form the visitor sends, a link, or a button that is disabled.

import { afterEach, describe, expect, it } from "vitest";

import { notPressable, press } from "../../src/pointer/pressing.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const at = (selector: string): Element => document.querySelector(selector) ?? document.body;

describe("a button pressed", () => {
  it("is one in a search form or outside any form, and its click is the one the site listens for", () => {
    document.body.innerHTML = `
      <form role="search"><input name="q"><button id="search" type="submit">Search times</button></form>
      <search><button id="tag" type="button">Search</button></search>
      <button id="more" type="button">Show more</button>`;
    let clicked = 0;
    at("#more").addEventListener("click", () => (clicked += 1));

    expect(notPressable(at("#search"))).toBeNull();
    expect(notPressable(at("#tag"))).toBeNull();
    expect(press(at("#more"))).toBeNull();
    expect(clicked).toBe(1);
  });

  it("is never one that sends a form, a link, a disabled button, or what is not a button", () => {
    document.body.innerHTML = `
      <form><input name="name"><button id="book" type="submit">Book my visit</button></form>
      <a href="/next"><button id="link" type="button">Next</button></a>
      <button id="off" disabled>Off</button>
      <p id="text">Words</p>`;

    expect(press(at("#book"))).toBe("it sends a form, which is the visitor's to send");
    expect(notPressable(at("#link"))).toBe("it leaves the page");
    expect(notPressable(at("#off"))).toBe("it is disabled");
    expect(notPressable(at("#text"))).toBe("it is not a button");
  });
});
