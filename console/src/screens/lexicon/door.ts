/** Lexicon doors: read the agent's three corners and set one. */

import { type LexiconAnswer, LexiconAnswerSchema, type LexiconBody } from "@pinecall/core/wire/rest-org";

import { put, read, type Credentials } from "@pinecall/core/api";

const lexiconOf = (agent: string): string => `/v1/agents/${encodeURIComponent(agent)}/lexicon`;

/** The agent's lexicon as this key sees it: own, team and production corners. */
export async function readLexicon(credentials: Credentials, agent: string): Promise<LexiconAnswer> {
  return LexiconAnswerSchema.parse(await read(credentials, lexiconOf(agent)));
}

/** Replace the corner's lexicon of the agent, guarded by the version it was read at. */
export async function setLexicon(credentials: Credentials, agent: string, lexicon: LexiconBody, ifVersion: number | null, note: string | null, team: boolean): Promise<LexiconAnswer> {
  return LexiconAnswerSchema.parse(await put(credentials, lexiconOf(agent), { lexicon, if_version: ifVersion, note, team }));
}
