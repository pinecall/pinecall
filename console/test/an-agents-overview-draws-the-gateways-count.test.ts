// An agent's Overview draws what the gateway counted over the window, a day at a time, however many
// calls it holds; the newest calls are read only for the few a reviewer should open first.

import { type SessionLine } from "@pinecall/core/wire/rest";
import { describe, expect, it } from "vitest";

import { callsOn, daysOf, windowWithCalls, worthALook } from "../src/screens/overview/counted.js";

const day = (date: string, phone: number, web: number) => ({ day: date, phone, web, whatsapp: 0, spend_usd: 0.05, judged: 2, passed: 1 });

describe("an agent's overview", () => {
  it("draws one bar a day of the window, a quiet day included, each by the channel the calls came in by", () => {
    const days = daysOf([day("2026-09-25", 0, 0), day("2026-09-26", 1, 1)]);
    expect(days.map((one) => one.day)).toEqual(["2026-09-25", "2026-09-26"]);
    expect(days.at(-1)?.calls).toEqual({ phone: 1, web: 1, whatsapp: 0 });
    expect(days.map(callsOn)).toEqual([0, 2]);
  });

  it("reads a day's judges as the calls a judge answered and those none broke", () => {
    expect(daysOf([day("2026-09-26", 1, 0)])[0]).toMatchObject({ judged: 2, held: 1, spend: 0.05 });
  });

  it("opens on today, else the last 7 days, else the last 30: the first window that holds a call", () => {
    const month = (quietFor: number) => daysOf(Array.from({ length: 30 }, (_, at) => day(`d${String(at)}`, at === 29 - quietFor ? 1 : 0, 0)));
    expect(windowWithCalls(month(0))).toBe(1);
    expect(windowWithCalls(month(6))).toBe(7);
    expect(windowWithCalls(month(7))).toBe(30);
    expect(windowWithCalls(month(30))).toBe(30);
  });

  it("lists first the newest calls a reviewer should open, six at most", () => {
    const call = (id: string, flags: SessionLine["flags"]) => ({ call: id, flags }) as SessionLine;
    const lines = [call("a", ["escalated"]), call("b", []), ...Array.from({ length: 8 }, (_, at) => call(`f${String(at)}`, ["low_score"]))];
    const worth = worthALook(lines).map((line) => line.call);
    expect(worth).toHaveLength(6);
    expect(worth[0]).toBe("a");
    expect(worth).not.toContain("b");
  });
});
