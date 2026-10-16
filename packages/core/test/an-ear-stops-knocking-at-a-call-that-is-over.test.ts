/** use-listen.ts: a join the listen door refused because the call ended is not asked again. */

import { expect, test } from "vitest";

import { GatewayError } from "../src/api";
import { refusedAs } from "../src/use-listen";

test("the door's 409 says the call is over, and nothing knocks again", () => {
  expect(refusedAs(new GatewayError(409, "call call_8260 is over: read its log or its recording instead"))).toBe("over");
});

test("any other refusal, or a room that did not open, may be asked again", () => {
  expect(refusedAs(new GatewayError(404, "no call call_8260"))).toBe("failed");
  expect(refusedAs(new GatewayError(503, "the gateway is draining"))).toBe("failed");
  expect(refusedAs(new Error("could not establish signal connection"))).toBe("failed");
});
