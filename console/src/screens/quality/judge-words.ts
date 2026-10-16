/** How one judge reads in a person's words: what it answers, when it runs, what it reads beyond the call. */

import type { JudgeRow } from "./judges-door";

/** What the judge answers: held or broke, one of its choices, or a score. */
export function answersOf(judge: Pick<JudgeRow, "answer" | "choices">): string {
  if (judge.answer === "choice") return `one of ${judge.choices.join(", ")}`;
  if (judge.answer === "score") return "a score, 1 to 5";
  return "held or broke";
}

/** When the judge runs: every call, a simulated one, or one its trigger says it applies to. */
export function whenOf(judge: Pick<JudgeRow, "when" | "trigger">): string {
  if (judge.when === "simulations") return "simulated calls";
  if (judge.when === "trigger") return `when: ${judge.trigger}`;
  return "every call";
}

/** What it reads beside the call and its tool calls; empty when nothing more. */
export function readsOf(judge: Pick<JudgeRow, "reads">): string {
  const said = { prompt: "the prompt", evidence: "the evidence", facts: "the call's facts" } as const;
  return judge.reads.map((read) => said[read]).join(", ");
}
