/** Dev verbs relayed by the gateway to the agent's `pinecall start` process. */

import { type DevVerb } from "@pinecall/core/wire/defs";

import { post, type Credentials } from "@pinecall/core/api";

// Verb → path family (the door's scope). Must match runtime api/agents/dev.py.
const FAMILY_OF: Record<DevVerb, "chat" | "knowledge" | "memory" | "evals" | "view"> = {
  "chat.roster": "chat",
  "chat.start": "chat",
  "chat.say": "chat",
  "chat.end": "chat",
  "view.render": "view",
  "knowledge.roster": "knowledge",
  "knowledge.push": "knowledge",
  "knowledge.eval": "knowledge",
  "memory.roster": "memory",
  "memory.eval": "memory",
  "memory.extraction": "memory",
  "simulate.start": "evals",
  "goldens.roster": "evals",
  "goldens.run": "evals",
  "promote.roster": "evals",
  "promote.write": "evals",
  "drift.read": "evals",
  "reproductions.roster": "evals",
  "reproductions.read": "evals",
};

/** `/v1/agents/<slug>/dev/<family>/<verb>`. */
export function devPath(agent: string, verb: DevVerb): string {
  return `/v1/agents/${encodeURIComponent(agent)}/dev/${FAMILY_OF[verb]}/${verb}`;
}

/** Send a dev verb; the caller parses the answer. */
export async function dev(credentials: Credentials, agent: string, verb: DevVerb, body: unknown = {}): Promise<unknown> {
  return post(credentials, devPath(agent, verb), body);
}
