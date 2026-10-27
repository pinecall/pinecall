// The pointer fills a field the way a person types, with the events a site's code listens for, takes a list's option by its words, tells an element that is no field what is typed for the site to write, and never touches a password, a card or a button.

import { afterEach, describe, expect, it } from "vitest";

import { TYPING_EVENT, fill, notFillable } from "../../src/pointer/typing.js";

afterEach(() => {
  document.body.innerHTML = "";
});

function aField(html: string): Element {
  document.body.innerHTML = html;
  const field = document.body.firstElementChild;
  if (field === null) throw new Error("no field");
  return field;
}

describe("filling a field", () => {
  it("types the words with an input event for each letter and a change at the end", async () => {
    const field = aField('<input name="name">');
    const heard: string[] = [];
    field.addEventListener("input", () => heard.push("input"));
    field.addEventListener("change", () => heard.push("change"));

    expect(await fill(field, "Jo", false)).toBeNull();
    expect((field as HTMLInputElement).value).toBe("Jo");
    expect(heard).toEqual(["input", "input", "input", "change"]);
  });

  it("chooses the option of a list whose words hold what was said, and names the options when none does", async () => {
    const list = aField("<select><option>Tuesday, Oct 28</option><option>Wednesday, Oct 29</option></select>");

    expect(await fill(list, "wednesday", true)).toBeNull();
    expect((list as HTMLSelectElement).value).toBe("Wednesday, Oct 29");
    expect(await fill(list, "Monday", true)).toBe('no option says "Monday": the options are "Tuesday, Oct 28", "Wednesday, Oct 29"');
  });

  it("refuses a password, a card, a hidden field and a button, and leaves them as they were", async () => {
    expect(notFillable(aField('<input type="password">'))).toBe("a password or a card is the visitor's to type");
    expect(notFillable(aField('<input autocomplete="cc-number">'))).toBe("a password or a card is the visitor's to type");
    expect(notFillable(aField('<input type="hidden">'))).toBe("a hidden field is not written in");
    expect(notFillable(aField("<button>Book</button>"))).toBe("it is not a field");
    const secret = aField('<input type="password">');
    expect(await fill(secret, "hunter2", true)).not.toBeNull();
    expect((secret as HTMLInputElement).value).toBe("");
  });

  it("tells an element that is no field what is typed, a letter at a time, when the site takes it", async () => {
    document.body.innerHTML = `<div id="editor"></div><div id="plain"></div>`;
    const editor = document.getElementById("editor")!;
    const told: [string, boolean][] = [];
    editor.addEventListener(TYPING_EVENT, (event) => {
      event.preventDefault();
      const { text, done } = (event as CustomEvent<{ text: string; done: boolean }>).detail;
      told.push([text, done]);
    });

    expect(await fill(editor, "ab", false)).toBeNull();
    expect(told).toEqual([["", false], ["a", false], ["ab", true]]);
    // Nothing of the site's takes it: no place to type.
    expect(await fill(document.getElementById("plain")!, "ab", false)).toBe("it is not a field");
  });
});
