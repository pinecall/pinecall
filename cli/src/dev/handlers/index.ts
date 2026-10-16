/** The console's dev verbs this process answers, one row per screen, over the agent's directory on disk. */

import { DevRefused, type DevHandler } from "@pinecall/agents/client";

import { chatHandlers } from "./chat.js";
import { knowledgeHandlers, memoryHandlers } from "./knowledge.js";
import { driftHandlers, promoteHandlers, reproductionHandlers } from "./runs.js";
import { refusalOf, type Here, type Screen, type Verbs } from "./screen.js";
import { goldenHandlers, simulateHandlers } from "./suite.js";

export type { Here, Screen, Verbs } from "./screen.js";

const NOT_HERE = (verb: string): string => `this process answers no ${verb}: nothing of it is in this directory`;

/** Every screen of one agent `pinecall start` answers. A new screen adds one line here. */
export function screensFor(here: Here): Screen[] {
  return [
    chatHandlers(here),
    goldenHandlers(here),
    simulateHandlers(here),
    knowledgeHandlers(here),
    memoryHandlers(here),
    promoteHandlers(here),
    driftHandlers(here),
    reproductionHandlers(),
  ];
}

/** The verb table adapted to the SDK's `DevHandler`; a refusal keeps its status and its sentence. */
export function devHandler(screens: Screen[]): DevHandler {
  const verbs: Verbs = Object.assign({}, ...screens.map((screen) => screen.verbs)) as Verbs;
  return async (verb, data) => {
    const answer = verbs[verb];
    if (answer === undefined) throw new DevRefused(404, NOT_HERE(verb));
    try {
      return (await answer(data)) as Record<string, unknown>;
    } catch (failed) {
      throw refusalOf(failed);
    }
  };
}
