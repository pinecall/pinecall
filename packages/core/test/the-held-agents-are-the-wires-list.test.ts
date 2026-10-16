/** agents.ts parses the agents door with the wire's schema and rejects renamed fields. */

import { expect, test } from "vitest";
import { z } from "zod";

import { readHeldAgents } from "../src/agents";

const CREDENTIALS = { base: "/", key: "pk_test" };

function answering(body: unknown): void {
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
}

test("the held agents are the door's rows, each with its channels and the corner holding it", async () => {
  answering({ agents: [{ slug: "recepcion", channels: ["phone", "web"], holder: { holder: "m_1", name: "Ana" } }, { slug: "citas", channels: ["phone"] }] });
  const agents = await readHeldAgents(CREDENTIALS);
  expect(agents.map((agent) => agent.slug)).toEqual(["recepcion", "citas"]);
  expect(agents[0]?.holder?.name).toBe("Ana");
});

test("a row the wire does not know is refused, never read by guess", async () => {
  answering({ agents: [{ name: "recepcion", channels: ["phone"] }] });
  await expect(readHeldAgents(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});
