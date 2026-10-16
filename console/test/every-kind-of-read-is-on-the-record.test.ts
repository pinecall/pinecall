/** Data & privacy's access log reads every kind of read the runtime writes, and refuses one it never named. */

import { expect, test } from "vitest";
import { z } from "zod";

import { readReads } from "../src/screens/org-data/door";

const CREDENTIALS = { base: "/", key: "pk_test" };
// runtime wire/rest/calls.py: ReadKind, every value.
const KINDS = ["log", "recording", "traceback", "listen", "supervise", "export", "memory"];

function answering(body: unknown): void {
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
}

test("every kind the runtime records is read, and a kind it never wrote is refused", async () => {
  answering({ reads: KINDS.map((what, at) => ({ subject: `call_${at}`, what, env: "production", reader: "m_ana", at })) });
  expect((await readReads(CREDENTIALS, null)).map((row) => row.what)).toEqual(KINDS);
  answering({ reads: [{ subject: "call_9", what: "glance", env: null, reader: "m_ana", at: 1 }] });
  await expect(readReads(CREDENTIALS, null)).rejects.toBeInstanceOf(z.ZodError);
});
