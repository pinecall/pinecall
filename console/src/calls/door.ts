/** What a person does with a call that is over, and who played a simulated one: the doors this page calls. */

import { z } from "zod";

import { drop, post, read, type Credentials } from "@pinecall/core/api";
import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { type PersonaRun, PersonaRunListSchema } from "@pinecall/core/wire/rest-evals";
import { GoldenSchema } from "@pinecall/core/wire/rest-goldens";

export type { PersonaRun };

const CaseSchema = z.looseObject({ name: z.string() });

const PromotedSchema = z.object({
  path: z.string(),
  candidate: GoldenSchema.required({ turns: true }),
  notes: z.array(z.string()),
});

/** A golden candidate written from a call: its file, the golden, and notes for review. */
export type Promoted = z.infer<typeof PromotedSchema>;

/** Keep a finished call as a case of the org's dataset; resolves to the name it was kept under. */
export async function keepCall(credentials: Credentials, call: string, name: string): Promise<string> {
  return CaseSchema.parse(await post(credentials, "/v1/evals/cases", { call, name })).name;
}

/** Write a golden candidate into `agents/<agent>/test/candidates`, in the directory of the agent's `pinecall start`. */
export async function promoteCall(credentials: Credentials, agent: string, call: string): Promise<Promoted> {
  return PromotedSchema.parse(await post(credentials, `/v1/agents/${encodeURIComponent(agent)}/dev/evals/promote.write`, { call }));
}

/** Run the hang-up judges over the call again; billed again, as the first judging was. */
export async function judgeAgain(credentials: Credentials, call: string): Promise<CallScore> {
  return CallScoreSchema.parse(await post(credentials, `/v1/evals/judge/${encodeURIComponent(call)}?again=true`, {}));
}

/** One ended call, its log, facts, memories and recording, erased for good. */
export async function eraseCall(credentials: Credentials, call: string): Promise<void> {
  await drop(credentials, `/v1/calls/${encodeURIComponent(call)}`);
}

/** The number onto the org's do-not-call list. */
export async function optOut(credentials: Credentials, number: string): Promise<void> {
  await drop(credentials, `/v1/org/consents/${encodeURIComponent(number)}`);
}

/** One simulated call's row: who played the caller and what it cost; null for a call no persona made. */
export async function readSimulation(credentials: Credentials, call: string): Promise<PersonaRun | null> {
  return PersonaRunListSchema.parse(await read(credentials, "/v1/simulations", { call })).runs[0] ?? null;
}
