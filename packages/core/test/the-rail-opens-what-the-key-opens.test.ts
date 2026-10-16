/** The nav rail shows only screens the key's scopes open; each screen is gated by one scope. */

import { expect, test } from "vitest";

import { notOpened, opens, SCOPE_OF } from "../src/scopes";

// The gateway's scope set (runtime types/key.py); a screen gated outside it could never open.
const KEY_SCOPES = ["app", "calls", "talk", "supervise", "pipeline", "words", "knowledge", "memory", "evals", "numbers", "keys", "providers", "team", "usage"];

test("every gated screen names a scope the gateway has", () => {
  for (const [screen, scope] of Object.entries(SCOPE_OF)) {
    expect(KEY_SCOPES, `${screen} is gated by ${scope}`).toContain(scope);
  }
});

test("a qa key reads calls and evals, and nothing it would be refused", () => {
  const qa = ["calls", "evals"];
  expect(["calls", "inbox", "evals", "agents"].every((screen) => opens(qa, screen))).toBe(true);
  expect(["talk", "pipeline", "settings", "lexicon", "docs", "org-docs", "memory", "numbers", "team", "usage"].some((screen) => opens(qa, screen))).toBe(false);
  // Every key can see its own tokens.
  expect(opens(qa, "tokens")).toBe(true);
});

test("a screen nobody gated is open to every key, and the sentence names the scope", () => {
  expect(opens([], "login")).toBe(true);
  expect(notOpened("team")).toBe("this key does not open team");
});
