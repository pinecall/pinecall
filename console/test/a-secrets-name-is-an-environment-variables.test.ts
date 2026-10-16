/** A secret's name is refused in the page as the gateway would refuse it. */

import { expect, test } from "vitest";

import { nameRefused } from "../src/screens/secrets/name";

test("a name is capitals, digits and underscores, starting with a capital", () => {
  expect(nameRefused("CRM_TOKEN")).toBeNull();
  expect(nameRefused("A1")).toBeNull();
  expect(nameRefused("crm_token")).not.toBeNull();
  expect(nameRefused("1TOKEN")).not.toBeNull();
  expect(nameRefused("_TOKEN")).not.toBeNull();
  expect(nameRefused("CRM-TOKEN")).not.toBeNull();
  expect(nameRefused("")).not.toBeNull();
});

test("a name the box sets itself is refused", () => {
  expect(nameRefused("PINECALL_KEY")).toMatch(/box's own/);
  expect(nameRefused("PINECALLER")).toBeNull();
});
