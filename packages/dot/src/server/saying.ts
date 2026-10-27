/** A sentence of a walk recorded when it is reached, once its slots are filled: the agent's voice, in real time, on the site's server. */
//
// A walk's sentence with `{slots}` cannot be recorded before the visitor says what fills them. The page
// asks for it by the walk, the step and the values; the sentence itself is read from the walks the agent
// published, never from the page, so a page asks the voice for the site's own sentences and nothing else:
// what a visitor brings is the values, one line of 80 characters each. The gateway records each text once
// and keeps it, so the same sentence with the same values costs nothing the second time.

import { filled, slotsOf, valueOf, type Values } from "../wire/acts.js";
import { MOST_HEARD, nextOf, notesOf, type ExplainRequest, type NextLine, type NextRequest, type Note, type SaidAnswer, type SayRequest } from "../wire/ask.js";
import { walksDocument, walksOf, type LiveStep, type RecordedWalk } from "../wire/index.js";

/** The agent whose voice records it, and the key the site's server holds for it. */
export interface Voicing {
  key: string;
  agent: string;
  /** Default `https://cloud.pinecall.io`. */
  gateway?: string | undefined;
  /** Which world the agent's walks and voice are read in: `sandbox` while it is held there. Default production. */
  env?: "sandbox" | "production" | undefined;
  /**
   * Whether a page may have its own text read aloud (`{ read }`, a page read with `reading`): any text of 480
   * characters said in the agent's voice. For a site whose door answers its own pages alone. Default no.
   */
  read?: boolean | undefined;
  /** Whether a page may have an output explained by the agent's model (`{ explain }`): a model asked per output. Default no. */
  explain?: boolean | undefined;
  /** Whether a page may have the dot talk to a chat for a goal (`{ next }`): Pinecall's caller asked per turn. Default no. */
  next?: boolean | undefined;
}

/** The most turns of its own a talk takes: the gateway's own ceiling on a caller's. */
const MOST_TURNS = 40;
const STYLE = "a person writing in a chat{language}: short turns, one or two lines, no narration";

/** The longest output a page may have explained. */
const LONGEST_EXPLAINED = 8000;

/** The longest text a page may have read in one request. */
const LONGEST_READ = 480;

const GATEWAY = "https://cloud.pinecall.io";
/** How long the walks a page reads are kept, in ms: as long as the gateway lets a page keep them. */
const KEPT_MS = 60_000;
const kept = new Map<string, { at: number; walks: RecordedWalk[] }>();

async function walksAt(url: string, ask: typeof fetch): Promise<RecordedWalk[]> {
  const hit = kept.get(url);
  if (hit !== undefined && Date.now() - hit.at < KEPT_MS) return hit.walks;
  const answer = await ask(url);
  const walks = answer.ok ? walksOf(await answer.json()) : [];
  kept.set(url, { at: Date.now(), walks });
  return walks;
}

/** The live step a request names, in the walks published for its page or, failing them, the home's. */
async function stepOf(request: SayRequest, voicing: Voicing, ask: typeof fetch): Promise<LiveStep> {
  const base = `${(voicing.gateway ?? GATEWAY).replace(/\/+$/, "")}/v1/agents/${encodeURIComponent(voicing.agent)}/public/`;
  const query = voicing.env === "sandbox" ? "?env=sandbox" : "";
  for (const document of new Set([walksDocument(request.path), "walks"])) {
    const walk = (await walksAt(`${base}${document}${query}`, ask)).find((one) => one.name === request.walk);
    const step = walk?.steps[request.step];
    if (step !== undefined && "live" in step) return step;
    if (walk !== undefined) break;
  }
  throw new Error(`the walk ${request.walk} has no sentence to record at step ${request.step}`);
}

/** Record a walk's sentence with its slots filled, in the agent's voice. Throws when the sentence is not the walk's or a slot is empty. */
export async function recordSay(request: SayRequest, voicing: Voicing, ask: typeof fetch = fetch): Promise<SaidAnswer> {
  const step = await stepOf(request, voicing, ask);
  const values: Values = {};
  for (const slot of slotsOf(step.say)) {
    const value = request.values[slot];
    if (typeof value === "string") values[slot] = valueOf(value);
  }
  const text = filled(step.say, values);
  if (text === null) throw new Error(`the walk ${request.walk}'s step ${request.step} needs ${slotsOf(step.say).join(", ")}`);
  return recorded(text, voicing, ask);
}

/** A text of the page itself recorded in the agent's voice: a part of a page read aloud. Throws unless the voicing lets a page read. */
export async function recordRead(text: string, voicing: Voicing, ask: typeof fetch = fetch): Promise<SaidAnswer> {
  if (voicing.read !== true) throw new Error("this door reads no page aloud: give its voicing read: true");
  const line = text.replace(/\s+/g, " ").trim();
  if (line === "" || line.length > LONGEST_READ) throw new Error(`a text read is 1 to ${LONGEST_READ} characters`);
  return recorded(line, voicing, ask);
}

/** An output explained by the agent's model, through the gateway: notes, each on one line of it. Throws unless the voicing lets a page explain. */
export async function explainOutput(request: ExplainRequest, voicing: Voicing, ask: typeof fetch = fetch): Promise<{ notes: Note[] }> {
  if (voicing.explain !== true) throw new Error("this door explains no output: give its voicing explain: true");
  const output = request.output.trim();
  if (output === "" || output.length > LONGEST_EXPLAINED) throw new Error(`an output explained is 1 to ${LONGEST_EXPLAINED} characters`);
  const answer = await ask(`${(voicing.gateway ?? GATEWAY).replace(/\/+$/, "")}/v1/agents/${encodeURIComponent(voicing.agent)}/explain`, {
    method: "POST",
    headers: { authorization: `Bearer ${voicing.key}`, "content-type": "application/json", ...(voicing.env === undefined ? {} : { "pinecall-env": voicing.env }) },
    body: JSON.stringify({ output, ...(request.command === undefined ? {} : { command: request.command.slice(0, 300) }), ...(request.language === undefined ? {} : { language: request.language }) }),
  });
  if (!answer.ok) throw new Error(`the gateway explained nothing: ${answer.status}`);
  return { notes: notesOf(await answer.json()) };
}

/** The dot's next line on a chat it talks to for a goal: Pinecall's caller, through the gateway, playing it. Throws unless the voicing lets a page talk. */
export async function nextLine(request: NextRequest, voicing: Voicing, ask: typeof fetch = fetch): Promise<NextLine> {
  if (voicing.next !== true) throw new Error("this door talks to no chat: give its voicing next: true");
  const goal = request.goal.trim();
  if (goal === "" || goal.length > 4000) throw new Error("a goal talked for is 1 to 4000 characters");
  const heard = request.heard.slice(-MOST_HEARD).map((turn) => ({ who: turn.who === "agent" ? "agent" : "caller", said: turn.said.slice(0, 4000) }));
  const mine = heard.filter((turn) => turn.who === "caller").length;
  const answer = await ask(`${(voicing.gateway ?? GATEWAY).replace(/\/+$/, "")}/v1/evals/caller`, {
    method: "POST",
    headers: { authorization: `Bearer ${voicing.key}`, "content-type": "application/json", ...(voicing.env === undefined ? {} : { "pinecall-env": voicing.env }) },
    body: JSON.stringify({
      persona: { goal, style: STYLE.replace("{language}", request.language === undefined ? "" : `, in the language "${request.language}"`) },
      heard,
      turns_left: Math.max(1, MOST_TURNS - mine),
    }),
  });
  if (!answer.ok) throw new Error(`the gateway said nothing: ${answer.status}`);
  const line = nextOf(await answer.json());
  if (line === null) throw new Error("the gateway gave no line");
  return line;
}

/** One text recorded by the gateway in the agent's voice, kept: the same text again costs nothing. */
async function recorded(text: string, voicing: Voicing, ask: typeof fetch): Promise<SaidAnswer> {
  const answer = await ask(`${(voicing.gateway ?? GATEWAY).replace(/\/+$/, "")}/v1/agents/${encodeURIComponent(voicing.agent)}/lines`, {
    method: "POST",
    headers: { authorization: `Bearer ${voicing.key}`, "content-type": "application/json", ...(voicing.env === undefined ? {} : { "pinecall-env": voicing.env }) },
    body: JSON.stringify({ texts: [text] }),
  });
  if (!answer.ok) throw new Error(`the gateway recorded nothing: ${answer.status}`);
  const body = (await answer.json()) as { lines?: { url: string; duration_ms: number; words: { text: string; start_ms: number; end_ms: number }[] }[] };
  const line = body.lines?.[0];
  if (line === undefined) throw new Error("the gateway recorded nothing");
  return { say: text, audio: line.url, durationMs: line.duration_ms, words: line.words.map((word) => ({ text: word.text, startMs: word.start_ms, endMs: word.end_ms })) };
}
