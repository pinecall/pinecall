/** Judges doors: the list a call meets (Pinecall's switched, the org's own, an agent's own), a judge written, switched, dropped or tried, and the model they run on. */

import { JudgeListSchema, JudgeTriedSchema, type JudgeRequest, type JudgeRow, type JudgeTried, type JudgeTry } from "@pinecall/core/wire/rest-evals";
import { JudgingSettingsSchema, type JudgingRequest, type JudgingSettings } from "@pinecall/core/wire/rest-org";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

export type { JudgeRequest, JudgeRow, JudgeTried, JudgingSettings };

/** Whose list: the org's (null: Pinecall's as the org switched them, and its own), or one agent's by its slug. */
export type Whose = string | null;

/** The owner the runtime gives Pinecall's own judges. */
export const PINECALL = "pinecall";

const door = (whose: Whose, name?: string): string =>
  `${whose === null ? "/v1/org" : `/v1/agents/${encodeURIComponent(whose)}`}/judges${name === undefined ? "" : `/${encodeURIComponent(name)}`}`;

export async function readJudges(credentials: Credentials, whose: Whose): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await read(credentials, door(whose))).judges;
}

/** Write one judge of one's own whole, or switch one of Pinecall's with `{ on }` alone; resolves to that list. */
export async function writeJudge(credentials: Credentials, whose: Whose, name: string, written: JudgeRequest): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await put(credentials, door(whose, name), written)).judges;
}

/** Forget one judge of one's own; resolves to that list. Pinecall's are switched off, never dropped. */
export async function dropJudge(credentials: Credentials, whose: Whose, name: string): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await drop(credentials, door(whose, name))).judges;
}

/** Ask one judge of the agent's newest finished calls; nothing is kept. */
export async function tryJudge(credentials: Credentials, agent: string, tried: JudgeTry): Promise<JudgeTried> {
  return JudgeTriedSchema.parse(await post(credentials, `/v1/agents/${encodeURIComponent(agent)}/judges/try`, tried));
}

export async function readJudging(credentials: Credentials): Promise<JudgingSettings> {
  return JudgingSettingsSchema.parse(await read(credentials, "/v1/org/judging"));
}

/** Judging on or off and the model it runs on, whole; resolves to what the gateway kept. */
export async function writeJudging(credentials: Credentials, written: JudgingRequest): Promise<JudgingSettings> {
  return JudgingSettingsSchema.parse(await put(credentials, "/v1/org/judging", written));
}
