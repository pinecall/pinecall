/** Sixty console logins are one line, the revoked are apart, and what was used last comes first. */

import { describe, expect, it } from "vitest";

import { sorted } from "../src/screens/tokens/bunches";
import type { Listed } from "../src/screens/tokens/door";

const row = (over: Partial<Listed>): Listed => ({
  fingerprint: Math.random().toString(36).slice(2),
  label: "console",
  kind: "person",
  env: null,
  name: "Bernardo",
  created_by: null,
  created_at: "2026-09-20T00:00:00Z",
  last_used_at: null,
  revoked_at: null,
  scopes: [],
  ...over,
});

describe("the token list", () => {
  it("makes one bunch of a person's keys with one label, newest use first", () => {
    const { mine } = sorted([row({}), row({ last_used_at: "2026-10-14T08:00:00Z" }), row({ label: "berna-air", last_used_at: "2026-10-13T08:00:00Z" })]);
    expect(mine.map((bunch) => [bunch.label, bunch.rows.length])).toEqual([["console", 2], ["berna-air", 1]]);
  });

  it("keeps servers, a person's keys and the revoked apart", () => {
    const { servers, mine, revoked } = sorted([row({ kind: "server", label: "web" }), row({}), row({ revoked_at: "2026-10-01T00:00:00Z" })]);
    expect([servers.length, mine.length, revoked.length]).toEqual([1, 1, 1]);
  });
});
