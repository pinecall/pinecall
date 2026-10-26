// The walks' menu has a field for what the visitor wants shown: it opens with no walks too, sends what was typed, and says what came of it.

import { afterEach, describe, expect, it } from "vitest";

import { Asking } from "../../src/pointer/asking.js";
import { Menu } from "../../src/pointer/menu.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

describe("the field for what to show", () => {
  it("opens with the menu even on a page with no walks, sends what was typed and clears it", () => {
    const asked: string[] = [];
    const asking = new Asking(document, (part) => document.body.append(part), { placeholder: "Ask me to show you…", onAsk: (text) => asked.push(text) });
    const menu = new Menu(document, (part) => document.body.append(part), {
      dock: "right",
      label: "Walks",
      more: "More walks",
      face: () => ({ at: { x: 900, y: 700 }, radius: 29 }),
      onPick: () => undefined,
      current: () => -1,
      ask: asking,
    });
    menu.offer([]);
    menu.available(true);
    const button = document.querySelector<HTMLButtonElement>(".pc-walks");
    expect(button?.hidden).toBe(false);

    button?.click();
    expect(asking.element.hidden).toBe(false);
    const input = asking.element.querySelector("input");
    if (input) input.value = "  where are the API keys?  ";
    asking.element.dispatchEvent(new Event("submit", { cancelable: true }));

    expect(asked).toEqual(["where are the API keys?"]);
    expect(input?.value).toBe("");
    menu.toggle(false);
    expect(asking.element.hidden).toBe(true);
    menu.close();
    asking.close();
  });

  it("says what came of it under the field, with one button to take it on", () => {
    let taken = 0;
    const asking = new Asking(document, (part) => document.body.append(part), { placeholder: "Ask", onAsk: () => undefined });
    const hint = asking.element.querySelector<HTMLElement>(".pc-ask-hint");

    asking.hint("That one is a question for the agent.", { label: "Ask the agent", onClick: () => (taken += 1) });
    expect([hint?.hidden, hint?.textContent]).toEqual([false, "That one is a question for the agent.Ask the agent"]);
    hint?.querySelector("button")?.click();
    expect(taken).toBe(1);
    asking.hint(null);
    expect(hint?.hidden).toBe(true);
    asking.close();
  });
});
