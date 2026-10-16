// call.started as the runtime writes it today: how the call is had, and the state it opens in.

import { expect, it } from "vitest";

import { CallStartedSchema } from "../src/wire/events-call";

it("reads a written call that opened in a state, and a spoken one that says nothing of either", () => {
  const written = {
    channel: "web",
    direction: "inbound",
    from: "web_c523",
    to: "front-desk",
    caller: null,
    started_at: 1791453433.2,
    env: "sandbox",
    medium: "text",
    state: { stage: "ask" },
  };
  const spoken = { channel: "phone", direction: "inbound", from: "+34600", to: "+34910", caller: null, started_at: 1.5 };

  expect(CallStartedSchema.parse(written)).toEqual(written);
  expect(CallStartedSchema.parse(spoken)).toEqual(spoken);
});

it("reads a simulation opened before expects, which carried its pass mark in two sentences", () => {
  const older = {
    channel: "web",
    direction: "inbound",
    from: "web_c523",
    to: "front-desk",
    persona: "hurried",
    accepts_when: "they get a time on Tuesday",
    declines_when: "",
    caller: null,
    started_at: 1.5,
  };

  expect(CallStartedSchema.parse(older).persona).toBe("hurried");
});
