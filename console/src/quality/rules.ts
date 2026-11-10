/** The rules the calls are held to, folded from the judges switched on and the scores read: how each held, the calls each broke, and how a judge is said in words. */

import { type Judgment } from "@pinecall/core/wire/events";
import { PINECALL, type JudgeRow } from "./door";
import type { Scored } from "./use-scores";

/** One rule: its judge, its words, and how it answered over the calls read. */
export interface Rule {
  name: string;
  said: string;
  held: number;
  settled: number;
  /** The judge behind it; null for one that answered a call and is no longer listed. */
  judge: JudgeRow | null;
}

/** The rules in force, the one that broke most first; a judge that answered and is not listed is still a rule. */
export function rulesOf(judges: readonly JudgeRow[] | null, scored: readonly Scored[]): Rule[] {
  const rules = new Map<string, Rule>();
  for (const judge of judges ?? []) {
    if (judge.on) rules.set(judge.name, { name: judge.name, said: judge.summary ?? judge.question, held: 0, settled: 0, judge });
  }
  for (const row of scored) {
    for (const judgment of row.score?.judges ?? []) {
      // Only a verdict counts: N/A and a classification answered neither held nor broken.
      if (judgment.verdict !== "held" && judgment.verdict !== "broken") continue;
      const rule = rules.get(judgment.name) ?? { name: judgment.name, said: judgment.name, held: 0, settled: 0, judge: null };
      rules.set(judgment.name, { ...rule, held: rule.held + (judgment.verdict === "held" ? 1 : 0), settled: rule.settled + 1 });
    }
  }
  return [...rules.values()].sort((one, other) => other.settled - other.held - (one.settled - one.held) || other.settled - one.settled);
}

export type Tone = "good" | "warn" | "bad";

/** A rule that holds this often is green, a little less amber, and under it red. */
export function toneOf(share: number): Tone {
  return share >= 0.95 ? "good" : share >= 0.9 ? "warn" : "bad";
}

/** How many of the calls read carry a score. */
export function judgedIn(scored: readonly Scored[]): number {
  return scored.filter((row) => row.score !== null && row.score.judges.length > 0).length;
}

/** A call one rule broke, with what its judge said of it. */
export interface Break {
  row: Scored;
  judgment: Judgment;
}

/** The calls a rule broke, newest first. */
export function brokenBy(rule: string, scored: readonly Scored[]): Break[] {
  return scored.flatMap((row) => {
    const judgment = row.score?.judges.find((judge) => judge.name === rule && judge.verdict === "broken");
    return judgment === undefined ? [] : [{ row, judgment }];
  });
}

/** A call that broke at least one rule, with every judge that broke on it. */
export interface BrokenCall {
  row: Scored;
  broke: Judgment[];
}

/** The calls read that broke a rule, newest first. */
export function brokenCalls(scored: readonly Scored[]): BrokenCall[] {
  return scored.flatMap((row) => {
    const broke = (row.score?.judges ?? []).filter((judge) => judge.verdict === "broken");
    return broke.length === 0 ? [] : [{ row, broke }];
  });
}

/** What the judge answers: held or broke, one of its choices, or a score. */
export function answersOf(judge: Pick<JudgeRow, "answer" | "choices">): string {
  if (judge.answer === "choice") return `One of ${judge.choices.join(", ")}`;
  if (judge.answer === "score") return "A score, 1 to 5";
  return "Held or broke";
}

/** When the judge runs: every call, a simulated one, or one its trigger says it applies to. */
export function whenOf(judge: Pick<JudgeRow, "when" | "trigger">): string {
  if (judge.when === "simulations") return "Simulated calls";
  if (judge.when === "trigger") return `When: ${judge.trigger}`;
  return "Every call";
}

const READS = { prompt: "the prompt", evidence: "the evidence", facts: "the call's facts" } as const;

/** What it reads beside the call and its tool calls; empty when nothing more. */
export function readsOf(judge: Pick<JudgeRow, "reads">): string {
  return judge.reads.map((read) => READS[read]).join(", ");
}

/** Whose the judge is, as a person says it. */
export function whoseOf(judge: Pick<JudgeRow, "owner">): string {
  if (judge.owner === PINECALL) return "Pinecall's";
  if (judge.owner === "org") return "Your org's";
  return judge.owner === "class" ? "The agent's code" : `${judge.owner}'s own`;
}
