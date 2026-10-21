/** The call pane's Models: the agent's ears, thinking and voice as the log's metrics name them, and the persona a simulated call was played by. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { decodeEntry } from "@pinecall/core/wire/codec";
import { type Entry } from "@pinecall/core/wire/envelope";
import { apply, initialState } from "@pinecall/core/wire/reduce";
import { expect, test } from "vitest";

import { agentModels, personaOf } from "../src/screens/call/models.js";

// The runtime's golden call, as the core holds it (packages/core/test/golden/).
const entries = (
  JSON.parse(readFileSync(fileURLToPath(new URL("../../packages/core/test/golden/call-log.json", import.meta.url)), "utf8")) as unknown[]
).map(decodeEntry);

test("the agent's three stages are the models its metrics name", () => {
  const models = agentModels(entries.reduce(apply, initialState()));
  expect([models.hears?.model, models.thinks?.model, models.speaks?.model]).toEqual(["stt-rt-v5", "claude-haiku-5-5", "eleven_flash_v2_5"]);
  expect(models.thinks?.provider).toBe("anthropic");
});

test("a stage that has not run yet names no model", () => {
  expect(agentModels(initialState())).toEqual({ hears: null, thinks: null, speaks: null });
});

test("a person's call has no persona, and a simulated one names the persona that played it", () => {
  expect(personaOf(entries)).toBeNull();
  const started = entries.find((entry) => entry.type === "call.started") as Entry;
  expect(personaOf([{ ...started, data: { ...started.data, persona: "in-a-hurry" } }])).toBe("in-a-hurry");
});
