// The corner's buttons: captions with hang-up in a call and with stop in a walk, into the corner while the face tours; the walks' button sized off the resting face.

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
  it("are captions and hang-up in a call, captions and stop in a walk, and none at rest", () => {
    const stopped: string[] = [];
    const person = aPerson(true, stopped);
    const shown = (): boolean[] => [".pc-calling", ".pc-cc", ".pc-hang", ".pc-stop"].map((selector) => !part(selector).hidden);

    person.buttons(true, false, true);
    expect(shown()).toEqual([true, true, true, false]);
    person.buttons(false, true, false);
    expect(shown()).toEqual([true, true, false, true]);
    expect(part(".pc-cc").getAttribute("aria-pressed")).toBe("false");
    part(".pc-stop").click();
    expect(stopped).toEqual(["stop"]);
    person.buttons(false, false, true);
    expect(shown()[0]).toBe(false);
    person.close();
  });

  it("keep stop alone in a walk where the site gives the visitor no captions to choose", () => {
    const person = aPerson(false);

    person.buttons(false, true, true);

    expect([part(".pc-cc").hidden, part(".pc-stop").hidden]).toEqual([true, false]);
    person.close();
  });

  it("slide into the face's corner while it tours, and aside as it comes home", () => {
    const person = aPerson(true);
    const layer = part(".pc-layer");

    person.tour(true);
    expect(layer.classList.contains("pc-away")).toBe(true);
    person.tour(false);
    expect(layer.classList.contains("pc-away")).toBe(false);
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
