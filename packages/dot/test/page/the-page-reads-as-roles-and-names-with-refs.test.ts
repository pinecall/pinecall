// The page reads as the accessibility tree does: roles and names, refs on what can be pointed at, sections out of view as one line, no values and no secrets.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Page } from "../../src/page/page.js";

const SITE = `
  <header><a href="/">Brightside Dental</a><nav aria-label="Main"><a href="#pricing">Pricing</a></nav></header>
  <main>
    <h1>A brighter smile</h1>
    <section aria-label="Book" id="book">
      <label for="name">Your name</label><input id="name" value="Jordan Lee">
      <input type="password" aria-label="Password" value="hunter2">
      <button>Book my visit</button>
    </section>
    <div data-pinecall-skip><button>Not the site's</button></div>
    <section aria-labelledby="faq-h" data-below><h2 id="faq-h">Questions</h2><button>Do you take my insurance?</button></section>
  </main>`;

beforeEach(() => {
  document.title = "Brightside";
  document.body.innerHTML = SITE;
  // happy-dom lays nothing out: what is marked below the fold is below it, the rest on the screen.
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const below = this.closest("[data-below]") !== null;
    const top = below ? 4000 : 100;
    return DOMRect.fromRect({ x: 0, y: top, width: 300, height: 40 });
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("the page as the agent reads it", () => {
  it("is one line per thing a person would name, with a ref on what can be pointed at", () => {
    const { text } = new Page(document).seen();

    expect(text).toContain('- link "Brightside Dental" [ref=');
    expect(text).toContain('- navigation "Main"');
    expect(text).toContain('- heading "A brighter smile" [level=1] [ref=');
    expect(text).toContain('- button "Book my visit" [ref=');
  });

  it("names a field by its label and never says its value; a password is not there at all", () => {
    const { text } = new Page(document).seen();

    expect(text).toContain('- textbox "Your name" [ref=');
    expect(text).not.toContain("Jordan Lee");
    expect(text).not.toContain("Password");
    expect(text).not.toContain("hunter2");
  });

  it("leaves out what the site marks as not its own", () => {
    expect(new Page(document).seen().text).not.toContain("Not the site's");
  });

  it("says a section out of view in one line, with where it is, and nothing inside it", () => {
    const { text } = new Page(document).seen();

    expect(text).toMatch(/- region "Questions" \[ref=e\d+\] \(below\)/);
    expect(text).not.toContain("insurance");
  });

  it("gives the same element the same ref every time, and finds it by role and name", () => {
    const page = new Page(document);
    const first = page.seen().text;
    const second = page.seen().text;
    const ref = page.find("button", "book my");

    expect(second).toBe(first);
    expect(ref).not.toBeNull();
    expect(page.element(ref ?? "")?.textContent).toBe("Book my visit");
  });

  it("finds what a person means by a name: the section before its heading, said exactly before said in part", () => {
    const page = new Page(document);
    page.seen();
    const questions = page.named("questions") ?? "";
    const book = page.named("Book") ?? "";

    expect(page.element(questions)?.getAttribute("aria-labelledby")).toBe("faq-h");
    expect(page.element(book)?.id).toBe("book");
    expect(page.named("Book my")).toBe(page.find("button", "Book my visit"));
    expect(page.named("nothing like it")).toBeNull();
  });

  it("finds a thing by its name inside a section out of view, which the snapshot shows as one line", () => {
    const page = new Page(document);
    page.seen();
    const ref = page.named("Do you take my insurance") ?? "";

    expect(page.seen().text).not.toContain("insurance");
    expect(page.element(ref)?.textContent).toBe("Do you take my insurance?");
  });

  it("still knows a ref whose element went off the screen, and none once it left the page", () => {
    const page = new Page(document);
    page.seen();
    const ref = page.find("button", "Book my visit") ?? "";
    document.querySelector("#book")?.setAttribute("data-below", "");
    page.seen();

    expect(page.element(ref)?.textContent).toBe("Book my visit");
    document.querySelector("#book")?.remove();
    expect(page.element(ref)).toBeNull();
  });
});
