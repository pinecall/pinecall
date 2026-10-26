/** What Jev is asked about what the visitor typed, and what its answers come to: the questions, the parts of the message a param is picked from, the decision. */
//
// Three questions on the same state, answered at once: what kind of thing they want (a walk, a thing
// shown, a person's answer, nothing), which walk, which thing of the page. And one more for each param of
// each walk: Jev cannot write, so a param in the visitor's words is a choice among the parts of what they
// typed (`spans`), one to five words in a row, or none; a param of a list, a choice among its options.
// So what fills a field is what the visitor wrote, never a word of the model's.

import { namedIn, type AskRequest, type Decision, type Named } from "../wire/ask.js";
import { valueOf, type Values } from "../wire/acts.js";

export const MODEL = "~typesafe/jev-latest";
export const THRESHOLD = 0.5;
/** The most options a Choice takes. */
export const MOST = 255;
/** The most words a part of the message picked as a param holds. */
const SPAN_WORDS = 5;
/** The roles a visitor asks to be shown first, when a page has more things than a Choice takes. */
const FIRST = ["region", "heading", "article", "group", "tab", "button", "link", "img", "form", "textbox", "combobox", "checkbox", "radio"];

const INTENTS = {
  walk: "they want to be shown around, told about a topic one of this page's walks covers, or something done that a walk does",
  show: "they want to see where one thing is on this page",
  talk: "they ask a question a person answers in words: advice, their own case, a price for them, help",
  none: "it is not about this site, or nothing on this page answers it",
};

/** Jev's answer to one question. */
export interface Answer {
  choice?: string;
  confidence?: number;
  probabilities?: Record<string, number>;
}

/** The things of the page the choice is among: every one with a name, the sections and headings first when there are too many. */
export function thingsOf(page: string): Named[] {
  const named = namedIn(page);
  if (named.length <= MOST) return named;
  const rank = (role: string): number => (FIRST.includes(role) ? FIRST.indexOf(role) : FIRST.length);
  const kept = new Set([...named].sort((a, b) => rank(a.role) - rank(b.role)).slice(0, MOST));
  return named.filter((thing) => kept.has(thing));
}

/**
 * The parts of what the visitor typed a param can be: one to five words in a row, as written, without the
 * commas and quotes around them. An email or a phone stays whole, being one word or two. The shorter first.
 */
export function spansOf(message: string): string[] {
  const words = [...message.matchAll(/\S+/g)].map((found) => ({ at: found.index, text: found[0] }));
  const trimmed = (text: string): string => text.replace(/^["'¿¡«“]+/, "").replace(/[,.;:!?"'»”]+$/, "");
  const spans: string[] = [];
  for (let size = 1; size <= SPAN_WORDS; size += 1) {
    for (let from = 0; from + size <= words.length; from += 1) {
      const first = words[from];
      const last = words[from + size - 1];
      if (first === undefined || last === undefined) continue;
      const span = trimmed(message.slice(first.at, last.at + last.text.length));
      if (span !== "" && !spans.includes(span)) spans.push(span);
    }
  }
  return spans.slice(0, MOST - 1);
}

/** The key a param's question is asked under: `param.<walk>.<name>`. */
const keyOf = (walk: string, param: string): string => `param.${walk}.${param}`;

/** The request Jev is asked: the state, and the questions on it. */
export function questionsOf(request: AskRequest, things: Named[], model = MODEL, spans = spansOf(request.message)): Record<string, unknown> {
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
  for (const walk of walks) {
    for (const [name, param] of Object.entries(walk.params ?? {})) {
      const options = param.oneOf ?? Object.fromEntries(spans.map((span, at) => [`s${at}`, `"${span}"`]));
      questions[keyOf(walk.name, name)] = {
        type: "choice",
        instructions:
          param.oneOf === undefined
            ? `If they want "${walk.title}": which part of what they typed is ${param.about}? "none" when they did not write it.`
            : `If they want "${walk.title}": which one is ${param.about}? "none" when they did not say.`,
        criteria: { none: "they did not say", ...options },
      };
    }
  }
  return { model, state: [state], questions };
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

/** The params of the walk decided, each one Jev was sure of: the part of the message, or the option. */
export function paramsFrom(answers: Record<string, Answer | undefined>, walk: AskRequest["walks"][number], spans: string[], threshold = THRESHOLD): Values {
  const values: Values = {};
  for (const [name, param] of Object.entries(walk.params ?? {})) {
    const answer = answers[keyOf(walk.name, name)];
    const choice = answer?.choice;
    if (choice === undefined || choice === "none" || (answer?.confidence ?? 0) < threshold) continue;
    const value = param.oneOf === undefined ? spans[Number(choice.slice(1))] : choice in param.oneOf ? choice : undefined;
    if (value !== undefined) values[name] = valueOf(value);
  }
  return values;
}
