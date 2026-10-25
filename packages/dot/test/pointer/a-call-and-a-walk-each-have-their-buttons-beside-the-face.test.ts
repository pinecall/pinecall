// The call's buttons sit in the corner; a walk's, captions and stop, ride on the face; the walks' button is sized off the resting face.

import { afterEach, describe, expect, it } from "vitest";

import { Person } from "../../src/pointer/person.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

function aPerson(captions: boolean, stopped: string[] = []): Person {
  return new Person(document, {
    dock: "right",
    label: "Talk to Pip",
    onClick: () => undefined,
    hangUp: { label: "Hang up", onClick: () => undefined },
    stop: { label: "Stop", onClick: () => stopped.push("stop") },
    captions: captions ? { label: "Captions", onClick: () => undefined } : null,
    explain: { label: "Explain this", onClick: () => undefined },
  });
}

const part = (selector: string): HTMLElement => document.querySelector<HTMLElement>(selector)!;

describe("the buttons beside the face", () => {
  it("are hang-up and captions in the corner in a call, captions and stop on the face during a walk, and none at rest", () => {
    const stopped: string[] = [];
    const person = aPerson(true, stopped);

    person.buttons(true, false, true);
    expect([part(".pc-calling").hidden, part(".pc-chips").hidden]).toEqual([false, true]);
    person.buttons(false, true, false);
    expect([part(".pc-calling").hidden, part(".pc-chips").hidden, part(".pc-cc-chip").hidden]).toEqual([true, false, false]);
    expect(part(".pc-cc-chip").getAttribute("aria-pressed")).toBe("false");
    part(".pc-stop").click();
    expect(stopped).toEqual(["stop"]);
    person.buttons(false, false, true);
    expect([part(".pc-calling").hidden, part(".pc-chips").hidden]).toEqual([true, true]);
    person.close();
  });

  it("keep stop alone during a walk where the site gives the visitor no captions to choose", () => {
    const person = aPerson(false);

    person.buttons(false, true, true);

    expect([part(".pc-chips").hidden, part(".pc-cc-chip").hidden, part(".pc-stop").hidden]).toEqual([false, true, false]);
    person.close();
  });

  it("take the face's radius from its resting size, touring or not", () => {
    const person = aPerson(true);
    person.face.style.setProperty("--pc-dot-size", "72px");

    person.tour(true);

    expect(person.radius).toBe(36);
    person.close();
  });
});
