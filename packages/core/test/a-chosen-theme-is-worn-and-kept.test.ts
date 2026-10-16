/** theme.ts choice mode: "auto" follows the system, an explicit choice persists. */

import { beforeEach, expect, test } from "vitest";

import { chooseTheme, chosenTheme, currentTheme, wearTheChosenTheme } from "../src/theme";

// No DOM: stubs for the root attribute, localStorage and the media query.
const kept = new Map<string, string>();
const root = { dataset: {} as Record<string, string> };
let systemIsLight = false;
let systemChanged: () => void = () => undefined;

function theSystemTurns(light: boolean): void {
  systemIsLight = light;
  systemChanged();
}

/** Simulate a reload: clear the document, keep storage. */
function reopened(): void {
  root.dataset = {};
  wearTheChosenTheme();
}

beforeEach(() => {
  kept.clear();
  root.dataset = {};
  systemIsLight = false;
  Object.defineProperty(globalThis, "document", { configurable: true, value: { documentElement: root } });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (name: string) => kept.get(name) ?? null,
        setItem: (name: string, value: string) => void kept.set(name, value),
        removeItem: (name: string) => void kept.delete(name),
      },
      matchMedia: () => ({
        get matches() {
          return systemIsLight;
        },
        addEventListener: (_: string, listener: () => void) => {
          systemChanged = listener;
        },
      }),
    },
  });
});

test("nothing chosen is auto, and auto wears the system's theme as it changes", () => {
  wearTheChosenTheme();
  expect(chosenTheme()).toBe("auto");
  expect(currentTheme()).toBe("dark");

  theSystemTurns(true);
  expect(currentTheme()).toBe("light");
});

test("a theme chosen outlasts the system changing its mind", () => {
  wearTheChosenTheme();
  expect(chooseTheme("dark")).toBe("dark");

  theSystemTurns(true);
  expect(currentTheme()).toBe("dark");
});

test("a theme chosen is what the next opening wears", () => {
  wearTheChosenTheme();
  chooseTheme("light");

  reopened();
  expect(chosenTheme()).toBe("light");
  expect(currentTheme()).toBe("light");
});

test("choosing auto again keeps nothing, and the system is back in charge", () => {
  wearTheChosenTheme();
  chooseTheme("light");
  expect(chooseTheme("auto")).toBe("dark");
  expect(kept.size).toBe(0);

  reopened();
  expect(chosenTheme()).toBe("auto");
});

test("a choice is not a flip: the console's flip is kept under a name of its own", () => {
  wearTheChosenTheme();
  chooseTheme("dark");
  expect([...kept.keys()]).toEqual(["pinecall.theme-choice"]);
});
