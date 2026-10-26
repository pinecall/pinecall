/** What the tutor does with what the visitor typed: the site's server decides, and it plays a walk, shows one thing, or offers the agent. */
//
// No call and no voice: a walk plays its recording, a thing is lit and pointed at with its name beside the
// face. Anything the page cannot show (a question a person answers, something not here, a server that
// did not answer) is never answered in words of the tutor's: the field says so, with the agent one click away.

import type { Page } from "../page/page.js";
import { decisionOf, namedIn, type AskRequest, type Decision } from "../wire/ask.js";

/** What the tutor says around a decision; the site's own words in its language. */
export interface AskWords {
  /** Beside the face while the server decides: "Looking…". */
  looking: string;
  /** Under the field when the page has nothing for it: "I can't find that on this page." */
  notHere: string;
  /** Under the field for a question a person answers: "That one is a question for the agent." */
  forAgent: string;
  /** The button that takes it to the agent: "Ask the agent". */
  agent: string;
}

/** The words, from the site's or in English. */
export function askWords(words: { looking?: string | undefined; notHere?: string | undefined; forAgent?: string | undefined; askAgent?: string | undefined } = {}): AskWords {
  return {
    looking: words.looking ?? "Looking…",
    notHere: words.notHere ?? "I can't find that on this page.",
    forAgent: words.forAgent ?? "That one is a question for the agent.",
    agent: words.askAgent ?? "Ask the agent",
  };
}

/** What doing it takes, from the tutor. */
export interface Asked {
  ask: (request: AskRequest) => Promise<unknown>;
  page: Page;
  path: () => string;
  walks: () => AskRequest["walks"];
  play: (walk: string) => void;
  /** Light and point at a thing, its name beside the face. */
  show: (element: Element, role: string, name: string) => void;
  /** Words beside the face for a moment; null takes them away. */
  note: (text: string | null) => void;
  /** A line under the field, with a button when there is somewhere to take it. */
  offer: (text: string, action?: { label: string; onClick: () => void }) => void;
  /** Take what they typed to the agent: a call, with it written in. None, no button. */
  talk?: ((message: string) => void) | undefined;
  words: AskWords;
}

/** Ask, and do the one thing decided; answers the decision, or null when the server gave none. */
export async function act(message: string, on: Asked): Promise<Decision | null> {
  on.note(on.words.looking);
  const seen = on.page.seen();
  let decision: Decision | null;
  try {
    decision = decisionOf(await on.ask({ message, path: on.path(), page: seen.text, walks: on.walks() }));
  } catch {
    decision = null;
  }
  on.note(null);
  const talk = on.talk;
  const agent = talk === undefined ? undefined : { label: on.words.agent, onClick: () => talk(message) };
  if (decision?.do === "walk") {
    on.play(decision.walk);
    return decision;
  }
  if (decision?.do === "show") {
    const target = decision.target;
    const element = on.page.element(target);
    const thing = namedIn(seen.text).find((one) => one.ref === target);
    if (element !== null && thing !== undefined) {
      on.show(element, thing.role, thing.name);
      return decision;
    }
  }
  on.offer(decision?.do === "talk" ? on.words.forAgent : on.words.notHere, agent);
  return decision;
}
