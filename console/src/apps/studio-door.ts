/** Making an agent in Studio: a name and what it starts as, how it sounds, and the release that answers in production. */

import { post, type Credentials } from "@pinecall/core/api";
import { setSettings } from "../configure/door";

export interface FirstDefinition {
  instructions: string;
  /** How it opens the call; null, the caller speaks first. */
  greeting: { say: string } | null;
  tools: never[];
  collect: null;
}

const doorOf = (name: string): string => `/v1/studio/agents/${encodeURIComponent(name)}`;

/** A new agent in the sandbox; with no definition it starts on the gateway's own first instructions. */
export async function makeStudioAgent(credentials: Credentials, name: string, definition?: FirstDefinition): Promise<void> {
  await post(credentials, "/v1/studio/agents", definition === undefined ? { name } : { name, definition });
}

/** The language the agent hears and speaks, the voice it speaks in and the zone its clock is read in, kept as the team's settings; each left out stays unset. */
export async function setSound(credentials: Credentials, agent: string, sound: { language: string; voice: string; timezone: string }): Promise<void> {
  const config = { ...(sound.language === "" ? {} : { language: sound.language }), ...(sound.voice === "" ? {} : { voice: sound.voice }), ...(sound.timezone === "" ? {} : { timezone: sound.timezone }) };
  await setSettings(credentials, agent, { config, if_version: null, note: "Chosen when the agent was made", team: true });
}

/** The sandbox's newest release kept as production's next, the deployer's settings with it: the agent answers there from the next call. */
export async function deployStudioAgent(credentials: Credentials, name: string, release: number): Promise<void> {
  await post(credentials, `${doorOf(name)}/deploy`, { release });
}
