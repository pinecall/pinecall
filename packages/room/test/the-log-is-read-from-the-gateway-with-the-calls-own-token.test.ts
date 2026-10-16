// With no relay, the page reads its call straight from the gateway, with the token minted for it.

import { expect, it } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { CALL, aRoom } from "./a-room-at-hand.js";

it("follows the gateway's log with the log token, and knows where the recording plays", async () => {
  const { store, gateway } = aRoom({ log: undefined, gateway: "https://gw.example/" });
  await store.start("chat");
  await settle();
  expect(gateway.requests[0]?.url).toBe(`https://gw.example/v1/calls/${CALL}/events?token=log_1`);
  expect(store.state.recording).toBe(`https://gw.example/v1/calls/${CALL}/recording?token=log_1`);
});

it("reads cloud.pinecall.io when no gateway is named", async () => {
  const { store, gateway } = aRoom({ log: undefined });
  await store.start("chat");
  await settle();
  expect(gateway.requests[0]?.url).toBe(`https://cloud.pinecall.io/v1/calls/${CALL}/events?token=log_1`);
});

it("follows a call it was dialled with the dial's own token", async () => {
  const { store, gateway } = aRoom({ log: undefined, callMe: async () => ({ call: "call_2", log_token: "log_2" }) });
  await store.callMe("+34600000001");
  await settle();
  expect(gateway.requests[0]?.url).toBe("https://cloud.pinecall.io/v1/calls/call_2/events?token=log_2");
});

it("fails in plain words when the server answered no token and there is no relay", async () => {
  const { store } = aRoom({ log: undefined, tokens: async () => ({ server_url: "wss://lk", participant_token: "t", call: CALL, log_token: "" }) });
  await store.start("chat");
  expect(store.state.phase).toBe("failed");
  expect(store.state.error).toContain("no log_token");
});

it("keeps no recording URL of its own when the tenant relays the log", async () => {
  const { store } = aRoom();
  await store.start("chat");
  expect(store.state.recording).toBe("");
});
