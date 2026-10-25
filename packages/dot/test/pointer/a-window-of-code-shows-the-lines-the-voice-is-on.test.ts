// A window of code opens beside the page when a step shows one, lights the lines the voice is on, dims the rest, and goes.

import { afterEach, describe, expect, it } from "vitest";

import { CodeWindow } from "../../src/pointer/code.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

const AGENT = { title: "agent.ts", text: "export class Desk extends Agent {\n  stage = \"identify\";\n\n  render() {}\n}" };

function aWindow(): CodeWindow {
  return new CodeWindow(document, (part) => document.body.append(part));
}

describe("a window of code", () => {
  it("is hidden until a step shows one, then holds its title and one numbered row a line", () => {
    const code = aWindow();
    const window = document.querySelector<HTMLElement>(".pc-code");
    expect(window?.hidden).toBe(true);

    code.show(AGENT, undefined);
    expect(window?.hidden).toBe(false);
    expect(window?.querySelector(".pc-code-bar span")?.textContent).toBe("agent.ts");
    expect([...document.querySelectorAll(".pc-code-line")].map((row) => row.textContent)).toEqual([
      "1export class Desk extends Agent {",
      '2  stage = "identify";',
      "3 ",
      "4  render() {}",
      "5}",
    ]);
  });

  it("lights the lines the voice is on and dims the others, and a later step lights others in the same window", () => {
    const code = aWindow();
    code.show(AGENT, [2, 2]);
    const lit = (): number[] => [...document.querySelectorAll(".pc-code-line")].flatMap((row, at) => (row.classList.contains("pc-on") ? [at + 1] : []));

    expect(document.querySelector(".pc-code")?.classList.contains("pc-lit")).toBe(true);
    expect(lit()).toEqual([2]);
    code.show(undefined, [4, 5]);
    expect(lit()).toEqual([4, 5]);
  });

  it("goes when a step shows none, and lights nothing while none is open", () => {
    const code = aWindow();
    code.show(AGENT, [1, 1]);
    code.show(null, undefined);

    expect(code.open).toBe(false);
    expect(document.querySelector<HTMLElement>(".pc-code")?.hidden).toBe(true);
    code.light([1, 1]);
    expect(code.open).toBe(false);
    code.close();
    expect(document.querySelector(".pc-code")).toBeNull();
  });
});
