/** `@pinecall/dot/server`: what the visitor typed to the dot, decided on a server by a model that only chooses, never writes. */
//
// One request to Jev, TypeSafe's System One model, through OpenRouter's Decisions API: three questions on
// the same state, answered at once. What kind of thing they want (a walk, a thing shown, a person's answer,
// nothing), which walk, and which thing of the page. Jev answers each with a choice among the options it
// was given and their probabilities: it cannot write a sentence or name a thing that is not on the page,
// so the dot does something on the page or offers the agent, and never talks. Under the threshold it does
// nothing rather than guess. The key is the server's: this never runs in a browser.

import { namedIn, type AskRequest, type Decision, type Named } from "../wire/ask.js";

export type { AskRequest, Decision } from "../wire/ask.js";

export interface DecideOptions {
  /** An OpenRouter key. */
  key: string;
  /** Default `~typesafe/jev-latest`. */
  model?: string | undefined;
  /** How sure the walk or the thing must be, 0 to 1, to be done. Default 0.5. */
  threshold?: number | undefined;
  /** Default OpenRouter's Decisions API. */
  endpoint?: string | undefined;
  fetch?: typeof fetch | undefined;
}

const ENDPOINT = "https://openrouter.ai/api/alpha/decisions";
const MODEL = "~typesafe/jev-latest";
const THRESHOLD = 0.5;
/** The most options a Choice takes. */
const MOST = 255;
/** The roles a visitor asks to be shown first, when a page has more things than a Choice takes. */
const FIRST = ["region", "heading", "article", "group", "tab", "button", "link", "img", "form", "textbox", "combobox", "checkbox", "radio"];

const INTENTS = {
  walk: "they want to be shown around, or told about a topic one of this page's walks covers",
  show: "they want to see where one thing is on this page",
  talk: "they ask a question a person answers in words: advice, their own case, a price for them, a booking, help",
  none: "it is not about this site, or nothing on this page answers it",
};

/** The things of the page the choice is among: every one with a name, the sections and headings first when there are too many. */
export function thingsOf(page: string): Named[] {
  const named = namedIn(page);
  if (named.length <= MOST) return named;
  const rank = (role: string): number => (FIRST.includes(role) ? FIRST.indexOf(role) : FIRST.length);
  const kept = new Set([...named].sort((a, b) => rank(a.role) - rank(b.role)).slice(0, MOST));
  return named.filter((thing) => kept.has(thing));
}

/** The request Jev is asked: the state, and the questions on it. */
export function questionsOf(request: AskRequest, things: Named[], model = MODEL): Record<string, unknown> {
  const walks = request.walks;
  const intents = walks.length > 0 ? INTENTS : { show: INTENTS.show, talk: INTENTS.talk, none: INTENTS.none };
  const state = [
    `A visitor is on the page ${request.path} of a website and typed to its guide: "${request.message}"`,
    "",
    "The things on the page (role and name):",
    ...things.map((thing) => `- ${thing.role} "${thing.name}"`),
    ...(walks.length > 0 ? ["", "The page's guided walks:", ...walks.map((walk) => `- ${walk.title}${walk.when ? `: ${walk.when}` : ""}`)] : []),
  ].join("\n");
  const questions: Record<string, unknown> = {
    intent: { type: "choice", instructions: "What does the visitor want the guide to do?", criteria: intents },
    target: {
      type: "choice",
      instructions: "Which one thing on the page is what they want to see, or best answers what they typed?",
      criteria: Object.fromEntries(things.map((thing) => [thing.ref, `${thing.role} "${thing.name}"`])),
    },
  };
  if (walks.length > 0) {
    questions["walk"] = {
      type: "choice",
      instructions: "Which of the page's guided walks is about what they typed?",
      criteria: Object.fromEntries(walks.map((walk) => [walk.name, `${walk.title}${walk.when ? `: ${walk.when}` : ""}`])),
    };
  }
  return { model, state: [state], questions };
}

interface Answer {
  choice?: string;
  confidence?: number;
  probabilities?: Record<string, number>;
}

/**
 * The one thing to do, from Jev's answers. To act (a walk or a thing shown) wins when the two together are
 * more likely than not, and of the two the surer one; under `threshold` it does nothing rather than guess.
 */
export function decisionFrom(answers: Record<string, Answer | undefined>, threshold = THRESHOLD): Decision {
  const p = answers["intent"]?.probabilities ?? {};
  const intent = answers["intent"]?.confidence ?? 0;
  const walk = answers["walk"];
  const target = answers["target"];
  if ((p["walk"] ?? 0) + (p["show"] ?? 0) >= 0.5) {
    const walking = (p["walk"] ?? 0) * (walk?.confidence ?? 0);
    const showing = (p["show"] ?? 0) * (target?.confidence ?? 0);
    if (walking >= showing && walk?.choice !== undefined && (walk.confidence ?? 0) >= threshold) return { do: "walk", walk: walk.choice, confidence: walk.confidence ?? 0 };
    if (target?.choice !== undefined && (target.confidence ?? 0) >= threshold) return { do: "show", target: target.choice, confidence: target.confidence ?? 0 };
    return { do: "none", confidence: intent };
  }
  return (p["talk"] ?? 0) >= (p["none"] ?? 0) ? { do: "talk", confidence: intent } : { do: "none", confidence: intent };
}

/** Decide what the dot does for what the visitor typed. Throws when the model cannot be reached or refuses. */
export async function decide(request: AskRequest, options: DecideOptions): Promise<Decision> {
  const things = thingsOf(request.page);
  const ask = options.fetch ?? fetch;
  const answer = await ask(options.endpoint ?? ENDPOINT, {
    method: "POST",
    headers: { authorization: `Bearer ${options.key}`, "content-type": "application/json" },
    body: JSON.stringify(questionsOf(request, things, options.model)),
  });
  if (!answer.ok) throw new Error(`the decision model answered ${answer.status}`);
  const body = (await answer.json()) as { answers?: Record<string, Answer> };
  const decision = decisionFrom(body.answers ?? {}, options.threshold);
  // A thing the model chose is one of the page's: anything else is no decision.
  if (decision.do === "show" && !things.some((thing) => thing.ref === decision.target)) return { do: "none", confidence: 0 };
  if (decision.do === "walk" && !request.walks.some((walk) => walk.name === decision.walk)) return { do: "none", confidence: 0 };
  return decision;
}
