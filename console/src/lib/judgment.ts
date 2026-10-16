/** One judge's answer about a call, said in a word wherever a page draws it. */

import type { Judgment } from "@pinecall/core/wire/events";

/** Held, broken, N/A, the choice or the score a classifying judge gave, or deferred and skipped as they are. */
export function answerOf(judgment: Pick<Judgment, "verdict" | "choice" | "score">): string {
  if (judgment.verdict === "classified") {
    if (judgment.choice !== null && judgment.choice !== undefined) return judgment.choice;
    return judgment.score === null || judgment.score === undefined ? "classified" : `${judgment.score}/5`;
  }
  return judgment.verdict === "na" ? "N/A" : judgment.verdict;
}
