/** `@pinecall/dot/server`: the site's door the dot asks, answered on its server: what the visitor typed decided, a row picked, a sentence recorded. */
//
// What the visitor typed goes to Jev, TypeSafe's System One model, through OpenRouter's Decisions API, as
// one request of questions answered at once (`questions.ts`): Jev answers each with a choice among the
// options it was given and their probabilities. It cannot write a sentence or name a thing that is not on
// the page, so the dot does something on the page or offers the agent, and never talks; a walk's params
// are parts of what was typed, never a word of the model's. Under the threshold it does nothing rather
// than guess. A walk that read a table asks which row answers the visitor best, the same way; a sentence
// with slots is recorded in the agent's voice when it is reached (`saying.ts`). The keys are the server's:
// this never runs in a browser.

import type { AskRequest, Decision, ExplainRequest, NextLine, NextRequest, Note, ReadRequest, RowAnswer, RowRequest, SaidAnswer, SayRequest } from "../wire/ask.js";
import { MODEL, MOST, THRESHOLD, decisionFrom, paramsFrom, questionsOf, spansOf, thingsOf, type Answer } from "./questions.js";
import { explainOutput, nextLine, recordRead, recordSay, type Voicing } from "./saying.js";

export type { AskRequest, Decision, DoorRequest, RowRequest, SayRequest } from "../wire/ask.js";
export type { Voicing } from "./saying.js";
export { decisionFrom, questionsOf, spansOf, thingsOf, recordSay, explainOutput, nextLine };

export interface DecideOptions {
  /** An OpenRouter key. */
  key: string;
  /** Default `~typesafe/jev-latest`. */
  model?: string | undefined;
  /** How sure the walk, the thing or a param must be, 0 to 1, to be done. Default 0.5. */
  threshold?: number | undefined;
  /** Default OpenRouter's Decisions API. */
  endpoint?: string | undefined;
  fetch?: typeof fetch | undefined;
}

export interface AnswerOptions extends DecideOptions {
  /** The agent whose voice records a walk's sentences with slots; none, a `say` is refused. */
  voicing?: Voicing | undefined;
}

const ENDPOINT = "https://openrouter.ai/api/alpha/decisions";

/** Ask Jev; its answers, by question. Throws when it cannot be reached or refuses. */
async function asked(body: Record<string, unknown>, options: DecideOptions): Promise<Record<string, Answer>> {
  const answer = await (options.fetch ?? fetch)(options.endpoint ?? ENDPOINT, {
    method: "POST",
    headers: { authorization: `Bearer ${options.key}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!answer.ok) throw new Error(`the decision model answered ${answer.status}`);
  return ((await answer.json()) as { answers?: Record<string, Answer> }).answers ?? {};
}

/** Decide what the dot does for what the visitor typed, and the params of a walk decided. Throws when the model cannot be reached or refuses. */
export async function decide(request: AskRequest, options: DecideOptions): Promise<Decision> {
  const things = thingsOf(request.page);
  const spans = spansOf(request.message);
  const answers = await asked(questionsOf(request, things, options.model ?? MODEL, spans), options);
  const decision = decisionFrom(answers, options.threshold ?? THRESHOLD);
  // A thing the model chose is one of the page's: anything else is no decision.
  if (decision.do === "show" && !things.some((thing) => thing.ref === decision.target)) return { do: "none", confidence: 0 };
  if (decision.do !== "walk") return decision;
  const walk = request.walks.find((one) => one.name === decision.walk);
  if (walk === undefined) return { do: "none", confidence: 0 };
  const params = paramsFrom(answers, walk, spans, options.threshold ?? THRESHOLD);
  return Object.keys(params).length === 0 ? decision : { ...decision, params };
}

/** Which row of a table best answers what the visitor typed; null when none is sure enough. */
export async function pickRow(request: RowRequest, options: DecideOptions): Promise<RowAnswer> {
  const rows = request.rows.slice(0, MOST);
  if (rows.length === 0) return { row: null };
  const answers = await asked(
    {
      model: options.model ?? MODEL,
      state: [`A visitor typed to a website's guide: "${request.message}"\n\nThe rows of the table the site shows them:\n${rows.map((row) => `- ${row}`).join("\n")}`],
      questions: { row: { type: "choice", instructions: "Which row best answers what they typed?", criteria: Object.fromEntries(rows.map((row, at) => [`r${at}`, row])) } },
    },
    options,
  );
  const choice = answers["row"];
  const at = Number(choice?.choice?.slice(1));
  return Number.isInteger(at) && at < rows.length && (choice?.confidence ?? 0) >= (options.threshold ?? THRESHOLD) ? { row: at } : { row: null };
}

/**
 * The site's door, whole: what the page sent (`{ decide }`, `{ row }` or `{ say }`), answered. Throws on a
 * request that is none of them, and on a model or a gateway that did not answer.
 */
export async function answer(body: unknown, options: AnswerOptions): Promise<Decision | RowAnswer | SaidAnswer | { notes: Note[] } | NextLine> {
  const request = (typeof body === "object" && body !== null ? body : {}) as Partial<Record<"decide" | "row" | "say" | "read" | "explain" | "next", unknown>>;
  if (isAsk(request.decide)) return decide(request.decide, options);
  if (isRow(request.row)) return pickRow(request.row, options);
  const voicing = (): Voicing => {
    if (options.voicing === undefined) throw new Error("this door records no sentence: give answer() a voicing");
    return options.voicing;
  };
  if (isSay(request.say)) return recordSay(request.say, voicing(), options.fetch ?? fetch);
  if (isRead(request.read)) return recordRead(request.read.text, voicing(), options.fetch ?? fetch);
  if (isExplain(request.explain)) return explainOutput(request.explain, voicing(), options.fetch ?? fetch);
  if (isNext(request.next)) return nextLine(request.next, voicing(), options.fetch ?? fetch);
  throw new Error("the door takes { decide }, { row }, { say }, { read }, { explain } or { next }");
}

const isString = (value: unknown): value is string => typeof value === "string";

function isAsk(value: unknown): value is AskRequest {
  const fields = (value ?? {}) as Record<string, unknown>;
  return typeof value === "object" && isString(fields["message"]) && isString(fields["path"]) && isString(fields["page"]) && Array.isArray(fields["walks"]);
}

function isRow(value: unknown): value is RowRequest {
  const fields = (value ?? {}) as Record<string, unknown>;
  return typeof value === "object" && isString(fields["message"]) && Array.isArray(fields["rows"]) && fields["rows"].every(isString);
}

function isNext(value: unknown): value is NextRequest {
  if (typeof value !== "object" || value === null) return false;
  const { goal, heard } = value as Record<string, unknown>;
  return typeof goal === "string" && Array.isArray(heard) && heard.every((turn: unknown) => typeof turn === "object" && turn !== null && typeof (turn as Record<string, unknown>)["said"] === "string");
}

function isExplain(value: unknown): value is ExplainRequest {
  return typeof value === "object" && value !== null && isString((value as Record<string, unknown>)["output"]);
}

function isRead(value: unknown): value is ReadRequest {
  return typeof value === "object" && value !== null && isString((value as Record<string, unknown>)["text"]);
}

function isSay(value: unknown): value is SayRequest {
  const fields = (value ?? {}) as Record<string, unknown>;
  const values = fields["values"];
  return typeof value === "object" && isString(fields["path"]) && isString(fields["walk"]) && Number.isInteger(fields["step"]) && typeof values === "object" && values !== null;
}
