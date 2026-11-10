/** What the Test tab draws, folded from what the doors answer: each golden's last result, each caller's last call, and a golden as a form holds it. */

import type { Expect, Golden, Step, Turn } from "@pinecall/core/wire/rest-goldens";
import type { EvalCase, Persona, Run } from "./door";
import type { PersonaRun } from "../simulations/door";

/** How a golden or a caller stood the last time it was played; `none` when it never was. */
export type Verdict = "held" | "broke" | "none";

/** A golden in the newest run that played it. */
export interface Result {
  verdict: "held" | "broke";
  /** Why it broke, each reason once. */
  reasons: string[];
  at: number;
  /** The call it was played on, to read the conversation. */
  call: string | null;
}

/** Each golden's result in the newest run that judged it, by name; `runs` newest first. A golden played under several models holds only when it held under each. */
export function resultsOf(runs: readonly Run[]): Map<string, Result> {
  const found = new Map<string, Result>();
  for (const run of runs) {
    if (run.matrix === null) continue;
    for (const golden of new Set(run.matrix.runs.map((cell) => cell.golden))) {
      if (found.has(golden)) continue;
      const failed = run.matrix.runs.filter((cell) => cell.golden === golden).flatMap((cell) => cell.scores.filter((score) => !score.passed));
      const reasons = [...new Set(failed.map((score) => (score.reason === "" ? score.metric : score.reason)))];
      found.set(golden, { verdict: reasons.length === 0 ? "held" : "broke", reasons, at: run.started_at, call: run.calls.find((one) => one.golden === golden)?.call ?? null });
    }
  }
  return found;
}

/** Each caller's newest call, by name; `runs` newest first. */
export function lastCalls(runs: readonly PersonaRun[]): Map<string, PersonaRun> {
  const found = new Map<string, PersonaRun>();
  for (const run of runs) if (run.persona !== null && !found.has(run.persona)) found.set(run.persona, run);
  return found;
}

/** How a caller's call went: every judge held, one broke, or nobody judged it yet. */
export function verdictOfCall(run: PersonaRun | undefined): Verdict {
  if (run === undefined || run.score === null || run.score.judged === 0) return "none";
  return run.score.passed ? "held" : "broke";
}

/** The cases that are goldens: approved by a person, or written by one. */
export const goldensIn = (cases: readonly EvalCase[]): EvalCase[] => cases.filter((one) => one.status === "approved");

/** The cases a judge kept that wait for a person. */
export const waitingIn = (cases: readonly EvalCase[]): EvalCase[] => cases.filter((one) => one.status === "pending");

/** The goldens a run played that the gateway keeps no case of: they live in the app's own folder. */
export function inTheCode(results: ReadonlyMap<string, Result>, cases: readonly EvalCase[]): string[] {
  const kept = new Set(cases.map((one) => one.name));
  return [...results.keys()].filter((name) => !kept.has(name)).sort();
}

/** What the caller says in a golden, in order; a backend's fact sent in its place reads as that. */
export function saidIn(golden: Golden): string[] {
  return (golden.turns ?? []).map((turn) => turn.say ?? `(the backend sends ${turn.event?.name ?? "an event"})`);
}

const quoted = (words: readonly string[]): string => words.map((word) => `“${word}”`).join(", ");

/** What must hold at the end, one phrase each, as a person reads it. */
export function demandsOf(expect: Expect | undefined): { tone: "must" | "never"; text: string }[] {
  if (expect === undefined) return [];
  return [
    ...(expect.says?.length ? [{ tone: "must" as const, text: `Says ${quoted(expect.says)}` }] : []),
    ...(expect.says_any?.length ? [{ tone: "must" as const, text: `Says one of ${quoted(expect.says_any)}` }] : []),
    ...(expect.not?.length ? [{ tone: "never" as const, text: `Never says ${quoted(expect.not)}` }] : []),
    ...(expect.tools?.length ? [{ tone: "must" as const, text: `Calls ${expect.tools.join(", ")}` }] : []),
    ...(expect.not_tools?.length ? [{ tone: "never" as const, text: `Never calls ${expect.not_tools.join(", ")}` }] : []),
    ...(expect.grounded === true ? [{ tone: "must" as const, text: "Answers from its knowledge" }] : []),
    ...(expect.register ? [{ tone: "must" as const, text: `Addresses the caller as ${expect.register === "tu" ? "tú" : "usted"}` }] : []),
    ...(expect.judges?.length ? [{ tone: "must" as const, text: `Holds for ${expect.judges.join(", ")}` }] : []),
  ];
}

// ── a golden's turns, as a person reads them ──

/** One step of what must follow a line, in words. */
export function stepWords(step: Step): { tone: "must" | "never"; text: string } {
  if ("tool" in step) {
    const args = Object.entries(step.args ?? {}).map(([name, value]) => `${name} = ${typeof value === "string" ? value : JSON.stringify(value)}`);
    return { tone: "must", text: `Calls ${step.tool}${args.length > 0 ? ` with ${args.join(", ")}` : ""}` };
  }
  if ("no_tool" in step) return { tone: "never", text: `Does not call ${step.no_tool}` };
  if ("end" in step) return { tone: "must", text: `The ${step.end} ends the call` };
  if ("nothing_else" in step) return { tone: "never", text: "Does nothing else in this turn" };
  const { says, says_any: any, not, intent } = step.reply;
  const parts = [...(says?.length ? [`says ${quoted(says)}`] : []), ...(any?.length ? [`says one of ${quoted(any)}`] : []), ...(not?.length ? [`never says ${quoted(not)}`] : []), ...(intent ? [`means: ${intent}`] : [])];
  return { tone: "must", text: `Replies${parts.length > 0 ? `, ${parts.join(", ")}` : ""}` };
}

/** The golden turn by turn: what goes in, and what must follow it in order. */
export function turnsOf(golden: Golden): { said: string; then: { tone: "must" | "never"; text: string }[] }[] {
  return (golden.turns ?? []).map((turn) => ({ said: turn.say ?? `(the backend sends ${turn.event?.name ?? "an event"})`, then: (turn.then ?? []).map(stepWords) }));
}

// ── a golden as the form holds it ──

/** One step as it is typed: lists as comma-separated words, arguments as JSON. */
export type StepForm =
  | { kind: "tool"; tool: string; args: string; within: number | null }
  | { kind: "no_tool"; tool: string }
  | { kind: "reply"; says: string; saysAny: string; never: string; intent: string; within: number | null }
  | { kind: "end"; by: "caller" | "agent" | "supervisor" | "platform" }
  | { kind: "nothing_else" };

/** A line the caller says with what must follow it; or a fact the backend sends, kept as it was. */
export type TurnForm = { say: string; steps: StepForm[] } | { event: Turn };

export interface GoldenForm {
  name: string;
  turns: TurnForm[];
  says: string;
  never: string;
  tools: string;
  neverTools: string;
  grounded: boolean;
  heldOut: boolean;
}

export const A_NEW_GOLDEN: GoldenForm = { name: "", turns: [{ say: "", steps: [] }], says: "", never: "", tools: "", neverTools: "", grounded: false, heldOut: false };

export const A_STEP: { readonly [Kind in StepForm["kind"]]: Extract<StepForm, { kind: Kind }> } = {
  tool: { kind: "tool", tool: "", args: "", within: null },
  no_tool: { kind: "no_tool", tool: "" },
  reply: { kind: "reply", says: "", saysAny: "", never: "", intent: "", within: null },
  end: { kind: "end", by: "agent" },
  nothing_else: { kind: "nothing_else" },
};

const listed = (typed: string): string[] => typed.split(",").map((one) => one.trim()).filter((one) => one !== "");
const joined = (words: readonly string[] | undefined): string => (words ?? []).join(", ");

function stepFormOf(step: Step): StepForm {
  if ("tool" in step) return { kind: "tool", tool: step.tool, args: step.args == null || Object.keys(step.args).length === 0 ? "" : JSON.stringify(step.args), within: step.within_ms ?? null };
  if ("no_tool" in step) return { kind: "no_tool", tool: step.no_tool };
  if ("end" in step) return { kind: "end", by: step.end };
  if ("nothing_else" in step) return { kind: "nothing_else" };
  return { kind: "reply", says: joined(step.reply.says), saysAny: joined(step.reply.says_any), never: joined(step.reply.not), intent: step.reply.intent ?? "", within: step.reply.within_ms ?? null };
}

// The step typed, or why it is none; `at` names it for the person ("line 2, step 1").
function stepOf(form: StepForm, at: string): Step | string {
  switch (form.kind) {
    case "tool": {
      if (form.tool.trim() === "") return `Name the tool of ${at}.`;
      let args: unknown = undefined;
      if (form.args.trim() !== "") {
        try {
          args = JSON.parse(form.args);
        } catch {
          return `The arguments of ${at} are not JSON: {"day": "thursday"}.`;
        }
        if (typeof args !== "object" || args === null || Array.isArray(args)) return `The arguments of ${at} are a JSON object: {"day": "thursday"}.`;
      }
      return { tool: form.tool.trim(), ...(args === undefined ? {} : { args: args as Record<string, unknown> }), ...(form.within === null ? {} : { within_ms: form.within }) };
    }
    case "no_tool":
      return form.tool.trim() === "" ? `Name the tool of ${at}.` : { no_tool: form.tool.trim() };
    case "end":
      return { end: form.by };
    case "nothing_else":
      return { nothing_else: true };
    case "reply": {
      const [says, any, not] = [listed(form.says), listed(form.saysAny), listed(form.never)];
      const intent = form.intent.trim();
      if (says.length + any.length + not.length === 0 && intent === "") return `Say what the reply of ${at} must say or mean.`;
      return { reply: { ...(says.length > 0 ? { says } : {}), ...(any.length > 0 ? { says_any: any } : {}), ...(not.length > 0 ? { not } : {}), ...(intent === "" ? {} : { intent }), ...(form.within === null ? {} : { within_ms: form.within }) } };
    }
  }
}

/** A golden a person wrote is rewritten here; one a call made is the call's, and the gateway refuses to rewrite it. */
export function fitsTheForm(kept: EvalCase): boolean {
  return kept.source === "person";
}

export function formOf(kept: EvalCase): GoldenForm {
  const expect = kept.golden.expect ?? {};
  const turns = (kept.golden.turns ?? []).map((turn): TurnForm => (typeof turn.say === "string" ? { say: turn.say, steps: (turn.then ?? []).map(stepFormOf) } : { event: turn }));
  return { name: kept.name, turns: turns.length > 0 ? turns : A_NEW_GOLDEN.turns, says: joined(expect.says), never: joined(expect.not), tools: joined(expect.tools), neverTools: joined(expect.not_tools), grounded: expect.grounded === true, heldOut: kept.held_out };
}

const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** The golden the form says, over what it was (so what the form does not draw is kept), or the first reason it says none. */
export function goldenOf(form: GoldenForm, was: Golden | undefined): { golden: Golden } | { refused: string } {
  const name = form.name.trim();
  if (!A_NAME.test(name)) return { refused: "Name it in lowercase words joined by dashes: never-quotes-a-price." };
  const turns: Turn[] = [];
  let line = 0;
  for (const turn of form.turns) {
    if ("event" in turn) {
      turns.push(turn.event);
      continue;
    }
    // A line left empty with nothing under it is a row nobody filled.
    if (turn.say.trim() === "" && turn.steps.length === 0) continue;
    line += 1;
    if (turn.say.trim() === "") return { refused: `Write what the caller says in line ${line}.` };
    const then: Step[] = [];
    for (const [at, step] of turn.steps.entries()) {
      const made = stepOf(step, `line ${line}, step ${at + 1}`);
      if (typeof made === "string") return { refused: made };
      then.push(made);
    }
    turns.push({ say: turn.say.trim(), ...(then.length > 0 ? { then } : {}) });
  }
  if (line === 0) return { refused: "Write at least one line the caller says." };
  const { says: _says, not: _not, tools: _tools, not_tools: _notTools, grounded: _grounded, ...rest } = was?.expect ?? {};
  const [says, not, tools, notTools] = [listed(form.says), listed(form.never), listed(form.tools), listed(form.neverTools)];
  const expect: Expect = { ...rest, ...(says.length > 0 ? { says } : {}), ...(not.length > 0 ? { not } : {}), ...(tools.length > 0 ? { tools } : {}), ...(notTools.length > 0 ? { not_tools: notTools } : {}), ...(form.grounded ? { grounded: true } : {}) };
  const { expect: _expect, ...kept } = was ?? { name };
  return { golden: { ...kept, name, turns, ...(Object.keys(expect).length > 0 ? { expect } : {}) } };
}

// ── a caller ──

export const isPinecalls = (caller: Persona): boolean => caller.owner === "pinecall";

/** Whether the app's code declares its callers: no door writes them then. */
export const setInCode = (callers: readonly Persona[]): boolean => callers.some((one) => one.fixed === true);

/** What a caller wants, in a line. */
export function aboutOf(caller: Persona): string {
  if (isPinecalls(caller)) return caller.summary ?? caller.goal;
  return caller.about !== "" ? caller.about : caller.goal;
}
