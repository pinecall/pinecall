// The corner's buttons: hang-up in a call alone, captions in a call and during a walk, and the walks' button sized off the resting face.

import { afterEach, describe, expect, it } from "vitest";

import { Person } from "../../src/pointer/person.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

function aPerson(captions: boolean): Person {
  return new Person(document, {
    dock: "right",
    label: "Talk to Pip",
    onClick: () => undefined,
    hangUp: { label: "Hang up", onClick: () => undefined },
    captions: captions ? { label: "Captions", onClick: () => undefined } : null,
    explain: { label: "Explain this", onClick: () => undefined },
  });
}

const part = (selector: string): HTMLElement => document.querySelector<HTMLElement>(selector)!;

describe("the corner's buttons", () => {
  it("show hang-up and captions in a call, captions alone during a walk, and nothing at rest", () => {
    const person = aPerson(true);

    person.buttons(true, false, true);
    expect([part(".pc-calling").hidden, part(".pc-hang").hidden, part(".pc-cc").hidden]).toEqual([false, false, false]);
    person.buttons(false, true, false);
    expect([part(".pc-calling").hidden, part(".pc-hang").hidden]).toEqual([false, true]);
    expect(part(".pc-cc").getAttribute("aria-pressed")).toBe("false");
    person.buttons(false, false, true);
    expect(part(".pc-calling").hidden).toBe(true);
    person.close();
  });

  it("show nothing during a walk where the site gives the visitor no captions to choose", () => {
    const person = aPerson(false);

    person.buttons(false, true, true);

    expect(part(".pc-calling").hidden).toBe(true);
    person.close();
  });

  it("take the face's radius from its resting size, touring or not", () => {
    const person = aPerson(true);
    document.documentElement.style.setProperty("--pc-dot-size", "72px");

    person.tour(true);

    expect(person.radius).toBe(36);
    person.close();
  });
});
