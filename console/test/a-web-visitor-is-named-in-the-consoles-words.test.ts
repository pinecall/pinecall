/** A web visitor is labelled "Web visitor · 3f7d" everywhere in the console (lib/format.ts). */

import { expect, test } from "vitest";

import { whoOn } from "@pinecall/core/calls";

import { visitorOf, webVisitor } from "../src/lib/format";

test("a visitor with no name and no number is the start of their id, as the list always said", () => {
  expect(visitorOf("web_abcd1234")).toBe("Web visitor · abcd");
  expect(visitorOf("call_3f7d8c21")).toBe("Web visitor · 3f7d");
  expect(visitorOf("+34612345678")).toBeNull();
  expect(visitorOf(null)).toBeNull();
});

test("whoOn with the console's words names the visitor the same, and a person or a number as before", () => {
  const line = { caller: null, direction: "inbound" as const, from: "call_3f7d8c21", to: null };
  expect(whoOn(line, webVisitor)).toBe("Web visitor · 3f7d");
  expect(whoOn({ ...line, caller: { name: "Lucía" } }, webVisitor)).toBe("Lucía");
  expect(whoOn({ ...line, from: "+34612345678" }, webVisitor)).toBe("+34 612 345 678");
});
