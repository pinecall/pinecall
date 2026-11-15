/** One session a key, kept between its requests and let go once idle. */

import { describe, expect, it } from "vitest";

import { IDLE_MS, Sessions } from "../src/sessions.js";

describe("the sessions", () => {
  it("are one a key, on the gateway the server hosts", () => {
    const sessions = new Sessions("https://cloud.example.com");
    const first = sessions.of("pk_one");
    expect(sessions.of("pk_one")).toBe(first);
    expect(sessions.of("pk_two")).not.toBe(first);
    expect([first.gateway, first.key, sessions.size]).toEqual(["https://cloud.example.com", "pk_one", 2]);
  });

  it("let go of a key nobody used for the idle time, and keep the one in use", async () => {
    let now = 0;
    const sessions = new Sessions("https://cloud.example.com", () => now);
    const idle = sessions.of("pk_idle");
    let closed = 0;
    idle.close = async () => void (closed += 1);
    sessions.of("pk_used");
    now = IDLE_MS - 1;
    const used = sessions.of("pk_used");
    now = IDLE_MS;
    await sessions.sweep();
    expect([closed, sessions.size]).toEqual([1, 1]);
    expect(sessions.of("pk_used")).toBe(used);
    expect(sessions.of("pk_idle")).not.toBe(idle);
  });

  it("hang every call up when the server closes", async () => {
    const sessions = new Sessions("https://cloud.example.com");
    let closed = 0;
    for (const key of ["pk_one", "pk_two"]) sessions.of(key).close = async () => void (closed += 1);
    await sessions.close();
    expect([closed, sessions.size]).toEqual([2, 0]);
  });
});
