/** The agent's walks: each macro file checked, the one a model means by a name, how the screen lists them, and their recording before any call. */
//
// Before any call, `recordWalks` records each sentence of each macro in the agent's voice and publishes
// them as `walks`, one document a page, for the page to play with no call. A sentence with `{slots}`
// cannot be recorded before the visitor fills them: it is published as a live step, recorded when it is
// reached. A step that acts (fill, press, wait, read) is published as it is, for the page to do.

import type { Serve } from "@pinecall/agents";

import { clock, isAct, macroOf, onPage, slotsOf, walksDocument, wordsOf, type Macro, type Param, type RecordedWalk, type Shown, type WalkStep } from "../wire/index.js";

/** How many sentences the gateway records in one request. */
const RECORDED_AT_ONCE = 64;

/** Each macro file, checked: `macros({ tour })` with `import tour from "./macros/tour.json" with { type: "json" }`. */
export function macros(files: Record<string, unknown>): Record<string, Macro> {
  return Object.fromEntries(Object.entries(files).map(([name, file]) => [name, macroOf(name, file)]));
}

/**
 * The walk a model means by `asked`: the one so named, else the one whose name it says among its words
 * ("site tour" for `tour`), else the only one there is. A model names a walk the way it heard it.
 */
export function walkNamed(walks: Record<string, Macro>, asked: string): Macro | undefined {
  const all = Object.values(walks);
  const words = wordsOf(asked);
  const said = (macro: Macro): boolean => wordsOf(macro.name).every((word) => words.includes(word));
  return walks[asked] ?? all.find((macro) => wordsOf(macro.name).join(" ") === words.join(" ")) ?? all.find(said) ?? (all.length === 1 ? all[0] : undefined);
}

/** The code a step shows beside the page, as the wire carries it: nothing when it shows none. */
export function shownBy(step: Shown): Shown {
  return { ...(step.code === undefined ? {} : { code: step.code }), ...(step.lines === undefined ? {} : { lines: step.lines }) };
}

/** What the page said the visitor played: `"tour", all 5 sentences` or `"tour", 2 of its 5 sentences`. */
export function walkedLine(data: Record<string, unknown>): string {
  const of = typeof data["of"] === "number" ? data["of"] : 0;
  const step = typeof data["step"] === "number" ? data["step"] : 0;
  return data["done"] === true ? `"${String(data["walk"])}", all ${of} sentences` : `"${String(data["walk"])}", ${step} of its ${of} sentences`;
}

/** A param as the screen lists it: `name: the visitor's name, in their words`, `plan: one of essential, family`. */
function paramLine(name: string, param: Param): string {
  return `${name}: ${param.about}, ${param.oneOf === undefined ? "in the visitor's own words" : `one of ${Object.keys(param.oneOf).join(", ")}`}`;
}

/** A walk as the screen lists it: its name, what it takes, and when to give it. */
export function walkLine(macro: Macro): string {
  const params = Object.entries(macro.params ?? {}).map(([name, param]) => paramLine(name, param));
  return `- ${macro.name}${params.length > 0 ? ` (params: ${params.join("; ")})` : ""}${macro.when ? `: when ${macro.when}` : ""}`;
}

/** Record each macro's sentences in the agent's voice and publish them, one document a page. A sentence recorded before costs nothing. */
export async function recordWalks(serve: Serve, walks: Macro[]): Promise<void> {
  if (walks.length === 0) return;
  // Only a sentence with no slot can be recorded now; one with slots waits for its values.
  const texts = walks.flatMap((walk) => walk.steps.flatMap((step) => (isAct(step) || slotsOf(step.say).length > 0 ? [] : [step.say])));
  const lines: Awaited<ReturnType<Serve["record"]>> = [];
  for (let at = 0; at < texts.length; at += RECORDED_AT_ONCE) lines.push(...(await serve.record(texts.slice(at, at + RECORDED_AT_ONCE))));
  let next = 0;
  const voice = lines[0]?.voice;
  const recorded: RecordedWalk[] = walks.map((walk) => ({
    name: walk.name,
    title: walk.title ?? walk.name,
    ...(walk.when === undefined ? {} : { when: walk.when }),
    ...(walk.pages === undefined ? {} : { pages: walk.pages }),
    ...(walk.params === undefined ? {} : { params: walk.params }),
    ...(voice === undefined ? {} : { voice }),
    steps: walk.steps.map((step): WalkStep => {
      if (isAct(step)) return step;
      const guards = { ...(step.if === undefined ? {} : { if: step.if }), ...(step.unless === undefined ? {} : { unless: step.unless }) };
      if (slotsOf(step.say).length > 0) return { say: step.say, beats: step.beats, live: true, ...shownBy(step), ...guards };
      const line = lines[next++];
      if (line === undefined) throw new Error(`${walk.name}: the gateway recorded fewer sentences than were asked`);
      return { say: step.say, audio: line.url, durationMs: line.durationMs, words: line.words, beats: step.beats, ...shownBy(step), ...guards };
    }),
  }));
  // One document a page: each is read by every visitor of its page, and is small. The home's is `walks`, with the
  // walks that name no page; a page that has walks of its own has `walks-<page>`, with those and the same walks.
  const pages = new Set(["/", ...walks.flatMap((walk) => walk.pages ?? [])]);
  for (const page of pages) {
    const here = recorded.filter((walk) => onPage(walk.pages, page));
    if (here.length > 0) await serve.publish(walksDocument(page), { walks: here });
  }
  for (const walk of recorded) {
    const ms = walk.steps.reduce((total, step) => total + ("durationMs" in step ? step.durationMs : 0), 0);
    const acts = walk.steps.filter((step) => isAct(step)).length;
    const live = walk.steps.filter((step) => "live" in step).length;
    const sentences = `${walk.steps.length - acts} sentences${live > 0 ? ` (${live} said live)` : ""}${acts > 0 ? ` · ${acts} acts` : ""}`;
    serve.say(`walk ${walk.name} · ${sentences} · ${clock(ms)} · ${voice ?? ""}`);
  }
}
