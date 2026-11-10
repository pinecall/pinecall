/** What the Judges page draws, folded from what the doors answer: the judges in their groups, how each held over the calls read, and an answer in a word. */

import { type Judgment } from "@pinecall/core/wire/events";
import type { Scored } from "../quality/use-scores";
import { PINECALL, type JudgeRow } from "./door";

/** How often a judge held, over the verdicts read: N/A and a classification answered neither. */
export interface Held {
  held: number;
  settled: number;
}

export function heldBy(scored: readonly Scored[]): Map<string, Held> {
  const found = new Map<string, Held>();
  for (const row of scored) {
    for (const judgment of row.score?.judges ?? []) {
      if (judgment.verdict !== "held" && judgment.verdict !== "broken") continue;
      const was = found.get(judgment.name) ?? { held: 0, settled: 0 };
      found.set(judgment.name, { held: was.held + (judgment.verdict === "held" ? 1 : 0), settled: was.settled + 1 });
    }
  }
  return found;
}

export type Show = "all" | "on" | "own";

export const SHOWS: readonly { show: Show; name: string }[] = [
  { show: "all", name: "All" },
  { show: "on", name: "On" },
  { show: "own", name: "Yours" },
];

const isLibrary = (judge: JudgeRow): boolean => judge.owner === PINECALL;

function shown(judge: JudgeRow, show: Show, typed: string): boolean {
  if (show === "on" && !judge.on) return false;
  if (show === "own" && isLibrary(judge)) return false;
  return typed === "" || `${judge.name} ${judge.question} ${judge.summary ?? ""}`.toLowerCase().includes(typed);
}

export interface Group {
  title: string;
  about: string;
  judges: JudgeRow[];
}

/** The active first, whoever's they are; then the rest by whose: the org's own, the agent's, and Pinecall's in two, the ones that guard a call and the ones that grade it. Empty groups are left out. */
export function groupsOf(judges: readonly JudgeRow[], agent: string, show: Show, search: string): Group[] {
  const these = judges.filter((judge) => shown(judge, show, search.trim().toLowerCase()));
  const inCode = these.some((judge) => judge.owner === "class");
  const shelves = (pool: readonly JudgeRow[]): Group[] => [
    { title: "Your org's own", about: "Asked of every agent's calls", judges: pool.filter((judge) => judge.owner === "org") },
    { title: `${agent}'s own`, about: inCode ? "Written in the agent's code" : "Asked of this agent's calls alone", judges: pool.filter((judge) => !isLibrary(judge) && judge.owner !== "org") },
    { title: "Recommended", about: "They guard every call. Switch these on first", judges: pool.filter((judge) => isLibrary(judge) && judge.recommended) },
    { title: "More from Pinecall", about: "They grade a call, when you want that signal", judges: pool.filter((judge) => isLibrary(judge) && !judge.recommended) },
  ];
  const active: Group = { title: "Active", about: "The ones switched on", judges: shelves(these.filter((judge) => judge.on)).flatMap((group) => group.judges) };
  return [active, ...shelves(these.filter((judge) => !judge.on))].filter((group) => group.judges.length > 0);
}

/** Whether this page may write the judge: one of the level in view, that no class declares. */
export function isOurs(judge: JudgeRow, agent: string): boolean {
  return judge.fixed !== true && judge.owner === (agent === "" ? "org" : agent);
}

/** Whether this page may switch it: one of Pinecall's that no class switches. */
export function isSwitched(judge: JudgeRow): boolean {
  return isLibrary(judge) && judge.fixed !== true;
}

/** What a judge said of a call, in a word. */
export function answerOf(judgment: Pick<Judgment, "verdict" | "choice" | "score">): string {
  if (judgment.verdict === "classified") {
    if (judgment.choice !== null && judgment.choice !== undefined) return judgment.choice;
    return judgment.score === null || judgment.score === undefined ? "Classified" : `${judgment.score}/5`;
  }
  if (judgment.verdict === "na") return "N/A";
  return judgment.verdict === "held" ? "Held" : judgment.verdict === "broken" ? "Broke" : judgment.verdict;
}

// The gateway's rule for the name call.score gives the answer.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const isAName = (name: string): boolean => A_NAME.test(name);
