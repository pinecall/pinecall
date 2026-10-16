// A pane dragged wider or narrower is found as it was left: its width kept in localStorage under
// `pinecall.pane.*`, per pane, and forgotten on request.

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { forgetWidth, keepWidth, keptWidth } from "../src/lib/preferences";

const kept = new Map<string, string>();

beforeEach(() => {
  kept.clear();
  (globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: (name: string) => kept.get(name) ?? null,
      setItem: (name: string, value: string) => void kept.set(name, value),
      removeItem: (name: string) => void kept.delete(name),
    },
  };
});

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe("a pane's width", () => {
  it("is kept as a whole number, under a name of the panes' own", () => {
    keepWidth("call.pane", 412.6);
    expect([...kept.entries()]).toEqual([["pinecall.pane.call.pane", "413"]]);
    expect(keptWidth("call.pane")).toBe(413);
  });

  it("is nothing when none was kept, or what was kept is not a width", () => {
    expect(keptWidth("call.pane")).toBeNull();
    kept.set("pinecall.pane.call.pane", "pk_not_a_number");
    expect(keptWidth("call.pane")).toBeNull();
  });

  it("is forgotten on a reset", () => {
    keepWidth("call.pane", 400);
    forgetWidth("call.pane");
    expect(keptWidth("call.pane")).toBeNull();
  });

  it("costs nothing where the browser refuses storage", () => {
    (globalThis as { window?: unknown }).window = {
      get localStorage(): never {
        throw new Error("denied");
      },
    };
    expect(() => keepWidth("call.pane", 400)).not.toThrow();
    expect(keptWidth("call.pane")).toBeNull();
  });
});
