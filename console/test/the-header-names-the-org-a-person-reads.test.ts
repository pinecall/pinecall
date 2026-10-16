// The header shows the org's name, not its id (same rule as the CLI's `cli/whoami.ts:orgOf`).

import { describe, expect, it } from "vitest";

import { orgOf } from "../src/lib/whoami";

const A_KEY = { key_id: "k_1", env: "sandbox" as const, scopes: [], production: false };

describe("whose org the header names", () => {
  it("is the slug, the word its people type", () => {
    expect(orgOf({ ...A_KEY, org: "org_98889a61509c", slug: "pinecall" })).toBe("pinecall");
  });

  it("falls back to the id when there is no slug, rather than showing nothing", () => {
    expect(orgOf({ ...A_KEY, org: "org_98889a61509c" })).toBe("org_98889a61509c");
    expect(orgOf({ ...A_KEY, org: "org_98889a61509c", slug: null })).toBe("org_98889a61509c");
  });
});
