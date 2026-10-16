/** use-floor.ts `refusal`: the gateway's message and HTTP status. */

import { expect, test } from "vitest";

import { GatewayError } from "../src/api";
import { refusal } from "../src/use-floor";

test("a key without calls is refused with 403 and the gateway's sentence, never the class's name", () => {
  const said = refusal(new GatewayError(403, "this key does not open calls; it opens talk"));
  expect(said).toEqual({ error: "this key does not open calls; it opens talk", refusedWith: 403 });
  expect(said.error).not.toContain("GatewayError");
});

test("a network that failed is no door's refusal: its sentence, and no status", () => {
  expect(refusal(new TypeError("Failed to fetch"))).toEqual({ error: "Failed to fetch", refusedWith: null });
});
