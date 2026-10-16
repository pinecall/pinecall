/** calls.ts: status, attention, duration and party of a call row, shared by every app. */

import { initialState } from "@pinecall/core/wire/reduce";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { describe, expect, it } from "vitest";

import { NOTHING, byDay, elapsed, isLive, isSpoken, prettyNumber, visitorId, wantsAPerson, whoOn } from "../src/calls";

const row = (fields: Partial<SessionLine>): SessionLine =>
  ({ call: "call_1", agent: "sofia", live: true, status: "active", direction: "inbound", from: null, to: null, caller: null, ...fields }) as SessionLine;

// Apps supply the wording around the visitor id.
const visitor = (id: string): string => `visitor ${id}`;

const asking = (status: "open" | "answered" | "lapsed") => ({ reason: "quiere hablar con alguien", wait_s: 60, status, asked_at: 100, by: null });

describe("a call as any app says it", () => {
  it("is live until the platform says it ended, ringing and dialling included", () => {
    for (const status of ["idle", "ringing", "dialing", "active"] as const) expect(isLive(row({ status }))).toBe(true);
    expect(isLive(row({ status: "ended" }))).toBe(false);
  });

  it("is spoken with a room, unless its caller sat down with a chat token — the widget's chat is a room too", () => {
    const seat = (identity: string, scope?: string) => ({ identity, kind: "caller" as const, joined_at: 1, speaking: false, attributes: scope === undefined ? {} : { "pinecall.scope": scope } });
    const room = (caller: string | null, ...participants: ReturnType<typeof seat>[]) => ({ room: { name: "call_1", sid: "RM_1", caller, participants } });
    expect(isSpoken({ room: null })).toBe(false);
    expect(isSpoken(room("web_1", seat("web_1", "chat")))).toBe(false);
    expect(isSpoken(room("web_1", seat("web_1", "talk")))).toBe(true);
    expect(isSpoken(room("sip_+34600", seat("sip_+34600")))).toBe(true);
    expect(isSpoken(room(null))).toBe(true);
  });

  it("wants a person only while the ask is open and the call is still up", () => {
    expect(wantsAPerson(row({ attention: asking("open") }))).toBe(true);
    expect(wantsAPerson(row({ attention: asking("answered") }))).toBe(false);
    expect(wantsAPerson(row({ attention: asking("lapsed") }))).toBe(false);
    expect(wantsAPerson(row({ status: "ended", attention: asking("open") }))).toBe(false);
    expect(wantsAPerson(row({}))).toBe(false);
  });

  it("says how long in minutes and seconds, hours once there are any, and a dash for no start", () => {
    expect(elapsed(100, 142)).toBe("0:42");
    expect(elapsed(100, 100 + 64)).toBe("1:04");
    expect(elapsed(100, 100 + 3600 + 65)).toBe("1:01:05");
    expect(elapsed(200, 100)).toBe("0:00");
    expect(elapsed(null, 100)).toBe(NOTHING);
  });

  it("names the caller, else the number that is not ours as a person dials it, else a web visitor in the app's words", () => {
    expect(whoOn(row({ caller: { name: "Lucía Pérez" }, from: "+34612345678" }), visitor)).toBe("Lucía Pérez");
    expect(whoOn(row({ from: "+34612345678" }), visitor)).toBe("+34 612 345 678");
    expect(whoOn(row({ direction: "outbound", from: "+34910000000", to: "+14176743169" }), visitor)).toBe("+1 (417) 674-3169");
    expect(whoOn(row({ from: "web_abcd1234" }), visitor)).toBe("visitor abcd");
    expect(whoOn(row({ from: "call_3f7d8c21" }), visitor)).toBe("visitor 3f7d");
    expect(whoOn(row({ from: "sip:desk@example.test" }), visitor)).toBe("sip:desk@example.test");
    expect(whoOn(row({}), visitor)).toBe(NOTHING);
  });

  it("names the caller of a folded call the same way it names a row", () => {
    expect(whoOn({ ...initialState(), caller: { name: "Lucía Pérez" }, from: "+34612345678" }, visitor)).toBe("Lucía Pérez");
    expect(whoOn({ ...initialState(), direction: "inbound", from: "+34612345678" }, visitor)).toBe("+34 612 345 678");
    expect(whoOn(initialState(), visitor)).toBe(NOTHING);
  });

  it("knows a web visitor by the start of their id, and nobody else", () => {
    expect(visitorId("web_abcd1234")).toBe("abcd");
    expect(visitorId("call_3f7d8c21")).toBe("3f7d");
    expect(visitorId("web_")).toBeNull();
    expect(visitorId("+34612345678")).toBeNull();
    expect(visitorId(null)).toBeNull();
    expect(visitorId(undefined)).toBeNull();
  });

  it("writes a number it has no pattern for as it came", () => {
    expect(prettyNumber("+59899123456")).toBe("+598 99 123 456");
    expect(prettyNumber("+4930123456")).toBe("+4930123456");
    expect(prettyNumber(null)).toBe(NOTHING);
  });
});

describe("calls cut by day", () => {
  // The console groups by UTC day; the phone passes its own.
  const utcDay = (at: number): string => new Date(at * 1000).toISOString().slice(0, 10);
  const NOW = Date.UTC(2026, 8, 23, 12) / 1000;
  const HOUR = 3600;
  const over = (call: string, started: number | null): SessionLine => row({ call, status: "ended", started_at: started });

  it("puts the live calls under live, then each day in the order given, the unstarted last", () => {
    const lines = [row({ call: "up", started_at: NOW - 60 }), over("noon", NOW - HOUR), over("dawn", NOW - 10 * HOUR), over("eve", NOW - 20 * HOUR), over("week", NOW - 100 * HOUR), over("never", null)];
    expect(byDay(lines, utcDay, NOW).map((day) => [day.name, day.lines.map((line) => line.call)])).toEqual([
      ["live", ["up"]],
      ["today", ["noon", "dawn"]],
      ["yesterday", ["eve"]],
      ["before", ["week"]],
      ["unstarted", ["never"]],
    ]);
  });

  it("gives a calendar day a moment on it to write its date from", () => {
    const [day] = byDay([over("week", NOW - 100 * HOUR)], utcDay, NOW);
    expect(day).toMatchObject({ key: "2026-09-19", name: "before", at: NOW - 100 * HOUR });
  });
});
