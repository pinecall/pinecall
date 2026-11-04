/** Judging as a terminal reads it: the judges table, a try, the org's judging, and a call's score. */

import type { CallScore } from "@pinecall/agents/wire";

import { BROKEN, clipped, count, formatHint, formatNotice, HELD, money } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { AgentJudging, Calibration, JudgeAgreement, JudgeList, JudgeListChanged, JudgeOwner, JudgeRow, JudgeTried, Judgment, JudgingReport } from "./service.js";

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
// Max width of a broken judge's reason under a call's score; `pinecall sessions <call> --json` has it whole.
const REASON = 110;

export const NO_JUDGES = (owner: JudgeOwner): string =>
  `${owner ?? "the org"} has no judges yet: \`pinecall judges add <name> --asks '…'\` (--org for every agent's), or the console's Judges`;

// A screen's width when stdout is no terminal: a pipe, a file, a test.
const A_SCREEN = 120;

/** One line per judge, cut at the screen's width: name, whose, on or off, how it answers, when it runs, and what it holds a call to. */
export function judges(owner: JudgeOwner, list: JudgeList, columns: number = A_SCREEN): string[] {
  if (list.judges.length === 0) return formatNotice(NO_JUDGES(owner));
  // Whether Pinecall recommends a library judge is `judges show`'s: the list keeps to its switch.
  const rows = table(
    ["name", "owner", "on", "answers", "when", "asks"],
    list.judges.map((row) => [row.name, row.owner, row.on ? "on" : "off", row.answer, whenLabel(row), textOf(row)]),
  ).map((line) => clipped(line, columns));
  const fixed = owner !== null && list.judges.some((row) => row.fixed === true);
  rows.push(formatHint("pinecall judges show <name> reads one", ...(fixed ? [`set in agents/${owner}/harness.* · judges({ on, own }) in the class`] : [])));
  return rows;
}

/** The rows written as code, one line each: the file and the name the class imports. */
export function pulled(done: { written: { path: string; symbol: string }[] }): string[] {
  if (done.written.length === 0) return ["nothing to pull: the agent has no judges of its own as rows"];
  return [...done.written.map((one) => `${one.path}  ${one.symbol}`), `${count(done.written.length, "judge")} written as code`, formatHint("add them to judges({ own }) in the class", "the rows stay until pinecall judges rm")];
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
  if (read.judges.length === 0) return formatNotice(NO_LABELS(owner));
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
  return `${list.done} · ${count(list.judges.length, "judge")} in the list`;
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

/** The org's judging in one line: on or off, the model, whose key, and whether evals are billed; a line more for `--agent`'s own. */
export function judging(report: JudgingReport): string {
  const said = [report.on ? "judging on" : "judging off — no call is judged at hang-up"];
  const model = report.model ?? null;
  const ceiling = report.ceiling_usd === null ? "" : ` · ceiling $${report.ceiling_usd.toFixed(2)} a call`;
  const own = report.agent === undefined ? [] : [agentJudging(report.agent, report)];
  if (model === null) return [[...said, `Pinecall's judge model · evals billed${ceiling}`].join(" · "), ...own].join("\n");
  said.push(`${model.provider}/${model.model}`);
  said.push(...optionsOf(model.options));
  said.push(report.own_key ? `your own ${model.provider} key: evals not billed` : `${model.provider} on a key Pinecall lends: evals billed${ceiling}`);
  return [said.join(" · "), ...own].join("\n");
}

// What the agent's calls are judged on: its own judge wins over the org's, a class's `@judge` over both.
function agentJudging(one: AgentJudging, org: JudgingReport): string {
  if (one.declared) return `  ${one.agent} · the class declares its own judge model, which wins over the settings and the org's`;
  if (one.judge === null) return `  ${one.agent} · no judge model of its own: its calls are judged as above${org.on ? "" : ", when judging is on"}`;
  const said = [one.agent, `judged on ${one.judge}`, ...optionsOf(one.options)];
  said.push(one.own_key ? "your own key: evals not billed" : "on a key Pinecall lends: evals billed");
  return `  ${said.join(" · ")}`;
}

function optionsOf(options: Record<string, unknown> | null | undefined): string[] {
  const kept = Object.entries(options ?? {}).map(([key, value]) => `${key}=${JSON.stringify(value)}`);
  return kept.length === 0 ? [] : [kept.join(" · ")];
}

/** One judgment as a line: its mark, what it answered (a word, a choice, a score out of 5), its reason, the seqs it cites. */
export function answerOf(judgment: Judgment): string {
  return `${MARK[judgment.verdict] ?? SKIPPED} ${wordOf(judgment)}  ${reasonOf(judgment)}${seqsOf(judgment)}`;
}

/** The judge's reason, or a placeholder when empty. */
export function reasonOf(said: { reason: string }): string {
  return said.reason === "" ? NO_REASON : said.reason;
}

/**
 * A call's score as printed: the headline, then the judges that broke with their reason and the
 * lines they cite, the ones that held by name, a classification with what it answered, the ones
 * that did not apply on one line; then what judging cost.
 */
export function callScore(score: CallScore): string[] {
  const width = Math.max(0, ...score.judges.map((judgment) => judgment.name.length));
  const broke = score.judges.filter((judgment) => judgment.verdict === "broken");
  const held = score.judges.filter((judgment) => judgment.verdict === "held");
  const classified = score.judges.filter((judgment) => judgment.verdict === "classified");
  const rest = score.judges.filter((judgment) => !broke.includes(judgment) && !held.includes(judgment) && !classified.includes(judgment));
  return [
    headline(score),
    ...broke.map((judgment) => `  ${BROKEN} ${judgment.name.padEnd(width)}  ${clipped(reasonOf(judgment), REASON)}${seqsOf(judgment)}`),
    ...held.map((judgment) => `  ${HELD} ${judgment.name}`),
    ...classified.map((judgment) => `  ${CLASSIFIED} ${judgment.name.padEnd(width)}  ${wordOf(judgment)}: ${reasonOf(judgment)}`),
    ...(rest.length === 0 ? [] : [`  ${NOT_APPLICABLE} ${rest.map((judgment) => judgment.name).join(" · ")}  did not apply`]),
    costLine(score),
  ];
}

// Four states: some broke, all held, judged with no verdict (only N/A and classifications), or not judged.
function headline(score: CallScore): string {
  if (score.passed === undefined || score.passed === null) {
    if (score.judges.some((judgment) => judgment.verdict === "na" || judgment.verdict === "classified")) {
      return `${NOT_APPLICABLE} no judge held or broke: the rest classified the call or did not apply`;
    }
    return `${SKIPPED} ${NOBODY_JUDGED}: ${score.not_judged ?? "the entry says nothing about why"}`;
  }
  const broke = score.judges.filter((judgment) => judgment.verdict === "broken").length;
  const settled = broke + score.judges.filter((judgment) => judgment.verdict === "held").length;
  return broke > 0 ? `${BROKEN} ${broke} of ${count(settled, "judge")} broke` : `${HELD} ${settled === 1 ? "the judge" : `all ${settled} judges`} held`;
}

// An unknown cost is omitted, not printed as zero; evals on the org's own key are never billed.
function costLine(score: CallScore): string {
  const judgeCalls = score.judge_calls;
  const evals = score.evals ?? 0;
  const priced = score.judge_cost_usd === undefined || score.judge_cost_usd === null ? "" : ` · ${money(score.judge_cost_usd)}`;
  const billed = score.own_key === true ? " · own key: evals not billed" : "";
  return `  ${count(judgeCalls, "judge call")} · ${count(evals, "eval")}${priced}${billed}`;
}

function seqsOf(judgment: Judgment): string {
  const seqs = judgment.evidence.seqs;
  return seqs.length === 0 ? "" : `  ${seqs.map((seq) => `#${seq}`).join(" ")}`;
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
