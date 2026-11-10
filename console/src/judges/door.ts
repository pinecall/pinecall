/** The judges' doors: the list a call meets, one written, switched, dropped or tried, each against the labels people gave, and the model they run on. */

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";
import { CalibrationSchema, JudgeListSchema, JudgeTriedSchema, type Calibration, type JudgeAgreement, type JudgeAnswer, type JudgeOn, type JudgeRead, type JudgeRequest, type JudgeRow, type JudgeTried } from "@pinecall/core/wire/rest-evals";
import { JudgingSettingsSchema, type JudgingRequest, type JudgingSettings, type ModelConfig } from "@pinecall/core/wire/rest-org";

export type { Calibration, JudgeAgreement, JudgeAnswer, JudgeOn, JudgeRead, JudgeRequest, JudgeRow, JudgeTried, JudgingSettings, ModelConfig };

/** The owner the runtime gives Pinecall's own judges. */
export const PINECALL = "pinecall";

const named = encodeURIComponent;

// With "" the org's list: Pinecall's as the org switched them, and its own. With a slug, that agent's.
const door = (agent: string, name?: string): string => `${agent === "" ? "/v1/org" : `/v1/agents/${named(agent)}`}/judges${name === undefined ? "" : `/${named(name)}`}`;

export async function readJudges(credentials: Credentials, agent: string): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await read(credentials, door(agent))).judges;
}

/** One judge of one's own written whole, or one of Pinecall's switched with `{ on }` alone; answers the list as it stands. */
export async function writeJudge(credentials: Credentials, agent: string, name: string, written: JudgeRequest): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await put(credentials, door(agent, name), written)).judges;
}

/** One judge of one's own forgotten; Pinecall's are switched off, never dropped. */
export async function dropJudge(credentials: Credentials, agent: string, name: string): Promise<JudgeRow[]> {
  return JudgeListSchema.parse(await drop(credentials, door(agent, name))).judges;
}

/** One judge asked of the agent's newest finished calls: by name alone, or as written and not yet kept. Nothing is kept; each answer is an eval. */
export async function tryJudge(credentials: Credentials, agent: string, name: string, written: JudgeRequest | null, last: number): Promise<JudgeTried> {
  return JudgeTriedSchema.parse(await post(credentials, `/v1/agents/${named(agent)}/judges/try`, { ...(written ?? {}), name, last }));
}

/** Each judge against the labels people gave on this world's calls: one agent's, or every agent's with "". */
export async function readAgreement(credentials: Credentials, agent: string): Promise<Calibration> {
  return CalibrationSchema.parse(await read(credentials, "/v1/evals/calibration", agent === "" ? {} : { agent }));
}

export async function readJudging(credentials: Credentials): Promise<JudgingSettings> {
  return JudgingSettingsSchema.parse(await read(credentials, "/v1/org/judging"));
}

/** Judging on or off and the model it runs on, written whole; answers what the gateway kept. */
export async function writeJudging(credentials: Credentials, written: JudgingRequest): Promise<JudgingSettings> {
  return JudgingSettingsSchema.parse(await put(credentials, "/v1/org/judging", written));
}
