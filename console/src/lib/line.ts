/** The phone a person tests from: said to the gateway once, and what a call from it reaches — the box's test line, or a production number. */

import { z } from "zod";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

/** `GET /v1/line/numbers`, and what `PUT /v1/line/from` answers. */
export const LineSchema = z.looseObject({
  /** The person's own phone, or none. */
  calling: z.array(z.string()),
  /** The agent a call from it reaches; null: the one agent the org holds. */
  agent: z.string().nullable().optional(),
  /** The box's own sandbox number to dial; null on a box with no test line. */
  test_line: z.string().nullable().optional(),
  /** The org's production numbers, each with the agent it rings. */
  numbers: z.array(z.object({ number: z.string(), agent: z.string() })),
});

export type Line = z.infer<typeof LineSchema>;

// A phone is said in the sandbox, whichever console this is: it is a sandbox copy a call reaches.
function sandbox(credentials: Credentials): Credentials {
  return { ...credentials, world: "sandbox" };
}

export async function readLine(credentials: Credentials): Promise<Line> {
  return LineSchema.parse(await read(sandbox(credentials), "/v1/line/numbers"));
}

/** This phone is the person's own; a call from it reaches the agent named, or the one the org holds. */
export async function sayPhone(credentials: Credentials, number: string, agent: string | null): Promise<Line> {
  return LineSchema.parse(await put(sandbox(credentials), "/v1/line/from", agent === null ? { number } : { number, agent }));
}

export async function forgetPhone(credentials: Credentials): Promise<void> {
  await drop(sandbox(credentials), "/v1/line/from");
}

/** What a call from the person's phone reaches right now, in one sentence; the agents are the slugs the org holds in the sandbox. */
export function whatAPhoneReaches(line: Line, held: readonly string[], mine: readonly string[]): { tone: "green" | "amber" | "gray"; said: string } {
  if (line.calling.length === 0) return { tone: "gray", said: "Nothing yet: say which phone is yours." };
  const agent = line.agent ?? (held.length === 1 ? held[0] : null);
  if (agent === null || agent === undefined) {
    return held.length === 0
      ? { tone: "amber", said: "No agent is running in the sandbox: deploy one, save one in Studio, or run pinecall start." }
      : { tone: "amber", said: `${String(held.length)} agents are running: pick the one your phone reaches.` };
  }
  if (!held.includes(agent)) return { tone: "amber", said: `${agent} is not running in the sandbox right now: a call reaches nothing.` };
  return mine.includes(agent)
    ? { tone: "green", said: `Your own copy of ${agent}, the one pinecall start holds.` }
    : { tone: "green", said: `${agent}, as the org runs it in the sandbox.` };
}
