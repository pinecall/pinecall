// A page reads its call with the call's own token, and the gateway answers the public projection: every entry of it reads and folds, the room seated and the turns kept.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { decodeEntry } from "../src/wire/codec.js";
import { reduce } from "../src/wire/reduce.js";

// The runtime's golden log as a participant reads it: projected by the runtime itself, and pinned
// there (tests/wire/golden/call-log.public.json), so this copy is what the gateway really sends.
const PUBLIC: unknown[] = JSON.parse(readFileSync(fileURLToPath(new URL("./fixtures/golden-call-log.public.json", import.meta.url)), "utf8"));

describe("a participant's reading of the log", () => {
  it("reads entry by entry, with no agent and no call in the envelope", () => {
    const entries = PUBLIC.map((raw) => decodeEntry(raw));

    expect(entries).toHaveLength(PUBLIC.length);
    expect(entries.every((entry) => entry.agent === undefined && entry.call === undefined)).toBe(true);
  });

  it("folds with nothing unreadable: the room opened, its people seated, the call ended", () => {
    const state = reduce(PUBLIC.map((raw) => decodeEntry(raw)));

    expect(state.errors).toEqual([]);
    expect(state.room?.participants.map((one) => one.kind)).toContain("agent");
    expect(state.status).toBe("ended");
  });

  it("keeps every turn of both sides, and the confirm the call asked for, settled", () => {
    const state = reduce(PUBLIC.map((raw) => decodeEntry(raw)));
    const turns = PUBLIC.filter((raw) => typeof raw === "object" && raw !== null && "type" in raw && (raw.type === "turn.user" || raw.type === "turn.agent"));

    expect(state.turns).toHaveLength(turns.length);
    expect(state.confirms.map((one) => one.status)).toEqual(["granted"]);
  });
});
