/** The world is the first segment of the page's path; the other world is the same screen with `/sandbox` put on or taken off. */

import { expect, test } from "vitest";

import { baseOf, inTheOtherWorld, inTheWorld, WORLD, WORLD_BASE, worldOf } from "../src/lib/mode";

test("a page at the root is production's, and one under /sandbox is the sandbox's", () => {
  expect(worldOf("/")).toBe("production");
  expect(worldOf("/calls/call_9f")).toBe("production");
  expect(worldOf("/sandbox")).toBe("sandbox");
  expect(worldOf("/sandbox/")).toBe("sandbox");
  expect(worldOf("/sandbox/a/clinica-norte/talk")).toBe("sandbox");
});

test("only the first segment says so: a word that merely starts with it, or sits deeper, does not", () => {
  expect(worldOf("/sandboxes")).toBe("production");
  expect(worldOf("/a/sandbox/talk")).toBe("production");
});

test("a page that was never rendered is production's, as one at the root is", () => {
  expect(WORLD).toBe("production");
  expect(WORLD_BASE).toBe("/");
});

test("the router's base is the root for production and /sandbox for the sandbox", () => {
  expect(baseOf("production")).toBe("/");
  expect(baseOf("sandbox")).toBe("/sandbox");
});

test("a router path is placed in a world by its base", () => {
  expect(inTheWorld("production", "/calls/call_9f")).toBe("/calls/call_9f");
  expect(inTheWorld("sandbox", "/calls/call_9f")).toBe("/sandbox/calls/call_9f");
  expect(inTheWorld("sandbox", "/")).toBe("/sandbox/");
});

test("the other world is the same screen with /sandbox put on", () => {
  expect(inTheOtherWorld("/a/clinica-norte/talk")).toBe("/sandbox/a/clinica-norte/talk");
  expect(inTheOtherWorld("/")).toBe("/sandbox/");
});

test("the other world is the same screen with /sandbox taken off", () => {
  expect(inTheOtherWorld("/sandbox/a/clinica-norte/talk")).toBe("/a/clinica-norte/talk");
  expect(inTheOtherWorld("/sandbox/")).toBe("/");
  expect(inTheOtherWorld("/sandbox")).toBe("/");
});

test("crossing twice lands where it started", () => {
  for (const path of ["/calls", "/sandbox/calls", "/a/norte/inbox/call_1", "/sandbox/settings/tokens"]) {
    expect(inTheOtherWorld(inTheOtherWorld(path))).toBe(path);
  }
});
