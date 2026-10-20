/** Judging as a terminal reads it: the judges table, a try, the org's judging, and a call's score. */

import type { CallScore } from "@pinecall/agents/wire";

import { BROKEN, HELD, money } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { Calibration, JudgeAgreement, JudgeList, JudgeListChanged, JudgeOwner, JudgeRow, JudgeTried, Judgment, JudgingReport } from "./service.js";

export { BROKEN, HELD };

const DEFERRED = "?";
const SKIPPED = "·";
const NOT_APPLICABLE = "–";
const CLASSIFIED = "=";

// LiveKit's three verdicts, and ours: never asked, did not apply, a choice or a score.
const MARK: Record<string, string> = { held: HELD, broken: BROKEN, deferred: DEFERRED, skipped: SKIPPED, na: NOT_APPLICABLE, classified: CLASSIFIED };
const WORD: Record<string, string> = { na: "n/a" };
const NOBODY_JUDGED = "nobody judged this call";
const NO_REASON = "no reason was written down";

export const NO_JUDGES = (owner: JudgeOwner): string =>
  `${owner ?? "the org"} has no judges yet: \`pinecall judges add <name> --asks '…'\` (--org for every agent's), or the console's Judges`;

/** One line per judge: name, whose, on or off, how it answers, when it runs, and what it holds a call to. */
export function judges(owner: JudgeOwner, list: JudgeList): string[] {
  if (list.judges.length === 0) return [NO_JUDGES(owner)];
  // A library judge Pinecall recommends says so beside its switch: the ones to turn on first.
  return table(
    ["name", "owner", "switch", "answers", "when", "asks"],
    list.judges.map((row) => [row.name, row.owner, `${row.on ? "on" : "off"}${row.recommended ? " · recommended" : ""}`, answerLabel(row), whenLabel(row), textOf(row)]),
  );
}

/** One judge whole: the line the list prints, then how and when it answers, what it reads, and its question. */
export function judge(row: JudgeRow): string[] {
  const lines = [
    `${row.name} · ${row.owner} · ${row.on ? "on" : "off"}${row.recommended ? " · recommended" : ""}`,
    `  answers  ${answerLabel(row)}`,
    `  when     ${whenLabel(row)}${row.when === "trigger" ? `: ${row.trigger}` : ""}`,
    `  reads    ${row.reads.length === 0 ? "the call alone" : row.reads.join(", ")}`,
  ];
  if (row.owner === "pinecall" && row.why) lines.push(`  why      ${row.why}`);
  lines.push(`  asks     ${row.question}`);
  if (row.author) lines.push(`  set by   ${row.author}`);
  return lines;
}

export const NO_LABELS = (owner: JudgeOwner): string =>
  `no judge of ${owner ?? "the org"} has been labelled yet: \`pinecall cases dismiss <case> --judge-was-wrong <judge>\` labels one, as does the console's Cases`;

/** One line per labelled judge: the labels, how many were compared and agreed, the rate, and whether it is trusted. */
export function agreement(owner: JudgeOwner, read: Calibration): string[] {
  if (read.judges.length === 0) return [NO_LABELS(owner)];
  const rows = table(
    ["judge", "labelled", "compared", "agreed", "rate", "trusted"],
    read.judges.map((row) => [row.judge, row.labelled, row.compared, row.agreed, rateOf(row), trustedOf(row, read)]),
  );
  return [...rows, `trusted from ${read.labels_to_judge} compared labels, agreeing with ${pct(read.agrees_at_least)} of them at least`];
}

function rateOf(row: JudgeAgreement): string {
  return row.rate === null ? "—" : pct(row.rate);
}

function trustedOf(row: JudgeAgreement, read: Calibration): string {
  if (row.trusted === null) return `? · ${read.labels_to_judge - row.compared} more to compare`;
  return row.trusted ? "yes" : "no";
}

function pct(share: number): string {
  return `${Math.round(share * 100)}%`;
}

export function changed(list: JudgeListChanged): string {
  return `${list.done} · ${list.judges.length} judge(s)`;
}

/** What a try answered: a line per call, then the evals and their cost. */
export function tried(one: JudgeTried): string[] {
  const wide = Math.max(0, ...one.rows.map((row) => row.call.length));
  const lines = one.rows.map((row) => {
    if (row.judgment === null) return `${row.call.padEnd(wide)}  · not judged: ${row.not_judged ?? "nothing said why"}`;
    return `${row.call.padEnd(wide)}  ${answerOf(row.judgment)}`;
  });
  return [...lines, `${one.evals} eval${one.evals === 1 ? "" : "s"} · ${money(one.cost_usd)} · nothing was written`];
}

/** The org's judging in one line: on or off, the model, whose key, and whether evals are billed. */
export function judging(report: JudgingReport): string {
  const said = [report.on ? "judging on" : "judging off — no call is judged at hang-up"];
  const model = report.model ?? null;
  const ceiling = report.ceiling_usd === null ? "" : ` · ceiling $${report.ceiling_usd.toFixed(2)} a call`;
  if (model === null) return [...said, `Pinecall's judge model · evals billed${ceiling}`].join(" · ");
  said.push(`${model.provider}/${model.model}`);
  const options = Object.entries(model.options ?? {}).map(([key, value]) => `${key}=${JSON.stringify(value)}`);
  if (options.length > 0) said.push(options.join(" · "));
  said.push(report.own_key ? `your own ${model.provider} key: evals not billed` : `${model.provider} on a key Pinecall lends: evals billed${ceiling}`);
  return said.join(" · ");
}

/** One judgment as a line: its mark, what it answered (a word, a choice, a score out of 5), its reason, the seqs it cites. */
export function answerOf(judgment: Judgment): string {
  return `${MARK[judgment.verdict] ?? SKIPPED} ${wordOf(judgment)}  ${reasonOf(judgment)}${seqsOf(judgment)}`;
}

/** The judge's reason, or a placeholder when empty. */
export function reasonOf(said: { reason: string }): string {
  return said.reason === "" ? NO_REASON : said.reason;
}

/** A call's score as printed: headline, one line per judge, then cost. */
export function callScore(score: CallScore): string[] {
  return [headline(score), ...score.judges.map(oneJudge), costLine(score)];
}

// Four states: passed, failed, judged with no verdict (only N/A and classifications), or not judged.
function headline(score: CallScore): string {
  if (score.passed === undefined || score.passed === null) {
    if (score.judges.some((judgment) => judgment.verdict === "na" || judgment.verdict === "classified")) {
      return `${NOT_APPLICABLE} no judge held or broke: the rest classified the call or did not apply`;
    }
    return `${SKIPPED} ${NOBODY_JUDGED}: ${score.not_judged ?? "the entry says nothing about why"}`;
  }
  return `${score.passed ? HELD : BROKEN} ${score.passed ? "every judge held" : "a judge answered broken"}`;
}

// A verdict reads as its reason; a classification and an N/A say what they answered first.
function oneJudge(judgment: Judgment): string {
  const answered = judgment.verdict === "classified" || judgment.verdict === "na" ? `${wordOf(judgment)}: ` : "";
  return `  ${MARK[judgment.verdict] ?? SKIPPED} ${judgment.name.padEnd(10)} ${answered}${reasonOf(judgment)}${seqsOf(judgment)}`;
}

// An unknown cost is omitted, not printed as zero; evals on the org's own key are never billed.
function costLine(score: CallScore): string {
  const judgeCalls = score.judge_calls;
  const evals = score.evals ?? 0;
  const priced = score.judge_cost_usd === undefined || score.judge_cost_usd === null ? "" : ` · ${money(score.judge_cost_usd)}`;
  const billed = score.own_key === true ? " · own key: evals not billed" : "";
  return `  ${judgeCalls} judge call${judgeCalls === 1 ? "" : "s"} · ${evals} eval${evals === 1 ? "" : "s"}${priced}${billed}`;
}

function seqsOf(judgment: Judgment): string {
  const seqs = judgment.evidence.seqs;
  return seqs.length === 0 ? "" : `  [seq ${seqs.join(", ")}]`;
}

function wordOf(judgment: Judgment): string {
  if (judgment.choice !== undefined && judgment.choice !== null) return judgment.choice;
  if (judgment.score !== undefined && judgment.score !== null) return `${judgment.score}/5`;
  return WORD[judgment.verdict] ?? judgment.verdict;
}

function answerLabel(row: JudgeRow): string {
  if (row.answer === "choice") return `choice: ${row.choices.join("|")}`;
  return row.answer === "score" ? "score 1-5" : "verdict";
}

function whenLabel(row: JudgeRow): string {
  return row.when === "trigger" ? "on a trigger" : row.when;
}

// The library's says what it saves you from, else its summary; an own judge's question is what it asks.
function textOf(row: JudgeRow): string {
  return row.owner === "pinecall" ? (row.why ?? row.summary ?? row.question) : row.question;
}
