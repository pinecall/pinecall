/** theme.ts flip mode: a flip persists across visits until the system theme changes. */

import { beforeEach, expect, test } from "vitest";

import { currentTheme, followTheSystemTheme, toggleTheme } from "../src/theme";

// No DOM: stubs for the root attribute, localStorage and the media query.
const kept = new Map<string, string>();
const root = { dataset: {} as Record<string, string> };
let systemIsLight = false;
let systemChanged: () => void = () => undefined;

function theSystemTurns(light: boolean): void {
  systemIsLight = light;
  systemChanged();
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

test("a page with nothing kept wears the system's theme, and follows it", () => {
  followTheSystemTheme();
  expect(currentTheme()).toBe("dark");

  theSystemTurns(true);
  expect(currentTheme()).toBe("light");
});

test("a flip is kept, and the next visit opens on it", () => {
  followTheSystemTheme();
  expect(toggleTheme()).toBe("light");

  root.dataset = {};
  followTheSystemTheme();
  expect(currentTheme()).toBe("light");
});

test("the system changing while the page is open undoes the flip", () => {
  followTheSystemTheme();
  toggleTheme();

  theSystemTurns(true);
  expect(currentTheme()).toBe("light");
  expect(kept.size).toBe(0);
});

test("the system changing while the page was closed undoes the flip", () => {
  followTheSystemTheme();
  toggleTheme();

  systemIsLight = true;
  root.dataset = {};
  followTheSystemTheme();
  expect(currentTheme()).toBe("light");
  expect(kept.size).toBe(0);
});

test("flipping back to the system's theme keeps nothing", () => {
  followTheSystemTheme();
  toggleTheme();
  toggleTheme();

  expect(currentTheme()).toBe("dark");
  expect(kept.size).toBe(0);
});
