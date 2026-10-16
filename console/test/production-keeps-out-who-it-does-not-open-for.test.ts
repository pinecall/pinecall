// `GET /v1/whoami` returns `production: false` rather than 403 for people without production
// access. Production's console shows its "No production access" card; the sandbox never does.

import { describe, expect, it } from "vitest";

import type { Whose } from "@pinecall/core/whoami";
import { keptOut } from "../src/lib/whoami";

const A_PERSON: Whose = { org: "org_1", slug: "norte", key_id: "k_1", env: "production", scopes: ["calls"], name: "Ana Ruiz", production: true };

describe("production's console", () => {
  it("stops a person production does not open for, naming them", () => {
    expect(keptOut("production", { ...A_PERSON, production: false })).toBe("Ana Ruiz has no production access: an admin gives it in Team.");
  });

  it("opens for a person with the switch, and for an operator visiting, whom the gateway answers true", () => {
    expect(keptOut("production", A_PERSON)).toBeNull();
    expect(keptOut("production", { ...A_PERSON, operator: true, visiting: true })).toBeNull();
  });
});

describe("the sandbox's console", () => {
  it("stops nobody", () => {
    expect(keptOut("sandbox", { ...A_PERSON, production: false, env: "sandbox" })).toBeNull();
  });
});
