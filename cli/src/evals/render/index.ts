/** Evals as a terminal reads them: the matrix, progress, runs, cases and groups, personas, a simulation, a replay. */

import { HELD, BROKEN, callScore } from "../../judging/render.js";
import { date } from "../../kit/format.js";
import { table } from "../../kit/table.js";
import type { CaseGroup, CaseList, Drift, EvalCase, EvalRun, GeneratedPersonas, JudgeDrift, Moved, Persona, Promoted, Rate, Replayed, Simulated } from "../service/index.js";
import { latencyLine } from "./matrix.js";

export { BottomBlock, header, progress, type Watched } from "./progress.js";
export { cellOf, latencyLine, matrix, suite } from "./matrix.js";

const NOTHING = "—";
export const NO_PERSONAS_YET = (agent: string): string => `${agent} has no personas yet: \`pinecall personas add <name> --goal '…' --style '…'\`, or the console's Personas`;

/** One line per run, newest first: id, when, agent, status, how much held. */
export function runs(found: EvalRun[]): string[] {
  return found.map((run) => {
    const cells = run.matrix?.runs.length ?? run.calls.length;
    const broken = new Set((run.matrix?.failures ?? []).map((one) => `${one.model} ${one.golden}`)).size;
    return `${run.id}  ${date(run.started_at)}  ${run.agent.padEnd(16)}  ${run.status.padEnd(7)}  ${cells - broken}/${cells}`;
  });
}

export function moved({ before, after, moved: found }: { before: string; after: string; moved: Moved[] }): string[] {
  if (found.length === 0) return [`${before} → ${after}`, "  nothing moved"];
  return [`${before} → ${after}`, ...found.map((one) => `  ${one.golden}  ${one.metric}  ${one.was} → ${one.now}${one.reason === "" ? "" : `  ${one.reason}`}`)];
}

export function promoted(done: Promoted, fromSeq: number): string[] {
  const turns = done.candidate.turns.filter((turn) => turn.say !== undefined).length;
  return [`${done.path}  ${turns} caller turn(s) from seq ${fromSeq}`, ...done.notes.map((note) => `  ${note}`)];
}

/** Each judge's held-rate over the window against the baseline, then the most recent broken calls. */
export function drift(found: Drift): string[] {
  const width = Math.max(1, ...found.judges.map((row) => row.judge.length));
  const lines = [
    `${found.agent}  drift  the last ${secondsAs(found.window)} against the ${secondsAs(found.baseline)} before it`,
    ...found.judges.map((row) => driftRow(row, width)),
    `  ${found.notJudged.now} not judged in the window, ${found.notJudged.before} in the baseline`,
  ];
  if (found.broke.length > 0) {
    lines.push(`  the ${new Set(found.broke.map((one) => one.call)).size} most recent broken call(s):`);
    for (const broke of found.broke) lines.push(`    ${broke.call}  ${broke.judge}  seq ${broke.seqs.join(", ")}  ${broke.reason}`);
  }
  return lines;
}

/** The inbox: how many wait, then one line a case — status, name, what broke, the env it came from, its age. */
export function cases(list: CaseList, status?: string, now = Date.now() / 1000): string[] {
  const waiting = `${list.pending} waiting of at most ${list.pending_at_most}`;
  if (list.cases.length === 0 && status !== undefined) return [waiting, `${list.agent} has no ${status} case`];
  if (list.cases.length === 0) return [waiting, `${list.agent} has no cases here: a call a judge broke on is kept at hang-up, or \`pinecall cases keep <call> --name x\``];
  return [waiting, ...table(["status", "name", "broke", "env", "age"], list.cases.map((one) => [one.status, one.name, brokeOf(one), one.source_env, ageOf(one.created_at, now)])).slice(1)];
}

/** One case whole: what broke and why, its turns, the state, the expect, where it came from, and what to type next. */
export function oneCase(one: EvalCase): string[] {
  const golden = one.golden;
  const version = one.source_version === null ? "" : `, settings v${one.source_version}`;
  const marks = [
    ...(one.held_out ? ["held out: played only when a run names it"] : []),
    ...(one.kept_in_repo ? ["kept in the repository: the nightly plays the file"] : []),
    ...(one.decided_by === null ? [] : [`${one.status} by ${one.decided_by}`]),
  ];
  return [
    `${one.name} · ${one.status} · ${one.agent}`,
    `  ${origin(one)}${version})${one.source === "person" ? "" : ` · kept by ${one.author}`} · ${date(one.created_at)}`,
    ...marks.map((line) => `  ${line}`),
    "",
    "  broke",
    ...(one.broke.length === 0 ? [`    ${NOTHING} nothing: ${one.source === "person" ? "a person wrote it, no call made it" : "a person kept it from a call that held"}`] : one.broke.map((broken) => `    ${broken.judge}  ${broken.reason}`)),
    "  the turns",
    ...golden.turns.flatMap((turn) => [`    ${turn.say === undefined ? `event ${turn.event?.name ?? ""} ${JSON.stringify(turn.event?.data ?? {})}` : `"${turn.say}"`}`, ...(turn.then ?? []).map((step) => `      then ${JSON.stringify(step)}`)]),
    `  state   ${JSON.stringify(golden.state ?? {})}`,
    ...(golden.memory === undefined || golden.memory.length === 0 ? [] : [`  memory  ${JSON.stringify(golden.memory)}`]),
    ...(golden.today === undefined ? [] : [`  today   ${golden.today}`]),
    `  expect  ${JSON.stringify(golden.expect ?? {})}`,
    "",
    ...nextForCase(one),
  ];
}

export function caseKept(one: EvalCase): string[] {
  return [`${one.name} kept · ${one.status} · ${one.agent} · from ${one.source_call}`, `  expect  ${JSON.stringify(one.golden.expect ?? {})}`];
}

// Where a case came from and who kept it, the parenthesis left open for the version: a call, or a person's hand.
function origin(one: EvalCase): string {
  return one.source === "person" ? `written by ${one.author} (by hand, ${one.source_env}` : `from ${one.source_call} (${one.source_env}`;
}

export function caseDecided(one: EvalCase, wrong?: string): string {
  if (one.status === "approved") return `${one.name} approved: the nightly plays it`;
  if (one.status === "pending") return `${one.name} pending again`;
  return `${one.name} dismissed${wrong === undefined ? "" : ` · ${wrong} labelled as wrong on ${one.source_call}`}`;
}

export function caseForgotten(one: EvalCase): string {
  return one.source === "person" ? `${one.name} forgotten` : `${one.name} forgotten: the call it came from, ${one.source_call}, stays`;
}

export function casePulled({ path, case: marked }: { path: string; case: EvalCase }): string[] {
  return [path, `${marked.name} is kept in the repository now: the nightly plays the file, not the case`];
}

/** One line a group: status, judge, how many calls and simulations, its cause, its id. */
/** A group in two lines: its status, judge, size, fix and id; under them, the cause the calls share. */
export function groupLines(group: CaseGroup): string[] {
  const sims = group.simulations === 0 ? "" : ` (${group.simulations} simulated)`;
  const fix = group.proposal ? ` · fix: ${group.proposal.kind} ${group.proposal.where}` : "";
  return [`${group.status.padEnd(9)} ${group.judge.padEnd(16)} ${String(group.cases).padStart(3)} call(s)${sims}${fix}  ${group.id}`, `          ${group.cause}`];
}

export function groups(agent: string, found: CaseGroup[]): string[] {
  return found.length === 0 ? [`${agent} has no case groups: nothing a judge broke on is waiting`] : found.flatMap(groupLines);
}

export function group({ group: one, cases: within }: { group: CaseGroup; cases: EvalCase[] }): string[] {
  return [...groupLines(one), ...within.map((each) => `  ${each.name} · ${each.source ?? "call"}${each.persona ? ` (${each.persona})` : ""} · ${each.source_call}`), ...nextForGroup(one)];
}

export function proposed(one: CaseGroup): string[] {
  return [...groupLines(one), ...nextForGroup(one)];
}

export const APPLIED = "applied as a new version of your settings · `pinecall test --case` replays the group's calls on it";

/** What to type next for a group, by what its proposal is. */
export function nextForGroup(one: CaseGroup): string[] {
  const proposal = one.proposal;
  if (proposal === undefined || proposal === null) return [`pinecall cases propose ${one.id}     ask the judge model for the cause and a fix`];
  const fix = [`  ${proposal.cause}`, `  proposes ${proposal.kind} · ${proposal.where} · ${typeof proposal.change === "string" ? proposal.change : JSON.stringify(proposal.change)} · ${Math.round(proposal.confidence * 100)}% sure`];
  if (proposal.kind === "setting") return [...fix, `pinecall cases apply ${one.id}       write it as a new version of your settings`];
  if (proposal.kind === "code") return [...fix, "  your assistant makes it: `pinecall mcp`, the cases tool, then `pinecall test --case`"];
  return fix;
}

/** Pinecall's first, then the agent's own; and a line when it has none of its own. */
export function personas(agent: string, found: Persona[], notPushed: string[] = []): string[] {
  const whose = (one: Persona): string => (one.owner === "pinecall" ? `pinecall ${one.on ? "on" : "off"}` : "yours");
  const rows = table(["name", "whose", "goal"], found.map((one) => [one.name, whose(one), one.owner === "pinecall" ? (one.summary ?? one.goal) : one.goal])).slice(1);
  const lines = found.some((one) => one.owner !== "pinecall") ? rows : [...rows, NO_PERSONAS_YET(agent)];
  if (notPushed.length > 0) lines.push(`${notPushed.length} written here and not pushed: ${notPushed.join(", ")} — \`pinecall personas push\` sends them`);
  return lines;
}

/** One persona whole: goal, style, models, what it expects, how it acts, facts. */
export function persona(one: Persona): string[] {
  const facts = Object.entries(one.facts);
  const acts = one.behavior;
  const behaving = [
    ...(acts.interrupts > 0 ? [`talks over ${Math.round(acts.interrupts * 100)}% of the answers`] : []),
    ...(acts.pause_s > 0 ? [`pauses ${acts.pause_s}s before each line`] : []),
    ...(acts.backchannels > 0 ? [`murmurs into ${Math.round(acts.backchannels * 100)}% of the answers`] : []),
    ...(acts.speed === 1 ? [] : [`speaks at ${acts.speed}× the vendor's tempo`]),
    ...(acts.interferer_db === null ? [] : [`a ${acts.ambience} ${acts.interferer_db} dB under it`]),
    ...(acts.packet_loss > 0 ? [`${Math.round(acts.packet_loss * 100)}% packets lost`] : []),
  ];
  const theRuntimes = "the runtime's";
  return [
    `${one.name} · ${one.goal}`,
    ...(one.owner === "pinecall" ? [`  Pinecall's · ${one.on ? "on" : "off"}${one.summary ? ` · ${one.summary}` : ""}`] : []),
    ...(one.about === "" ? [] : [`  ${one.about}`]),
    `  ${one.style}`,
    `  played by ${one.llm ?? theRuntimes} · read by ${one.tts ?? theRuntimes} · voice ${one.voice ?? theRuntimes}`,
    ...(behaving.length === 0 ? [] : [`  on a spoken line: ${behaving.join(", ")}`]),
    ...(one.expects.length === 0 ? ["  (expects nothing: the expected-outcome judge answers N/A on its calls)"] : one.expects.map((line) => `  expects: ${line}`)),
    ...(one.tags.length === 0 ? [] : [`  tags: ${one.tags.join(", ")}`]),
    ...(facts.length === 0 ? ["  (no facts: this caller may state nothing about themselves)"] : facts.map(([what, said]) => `  ${what}: ${said}`)),
  ];
}

export function personaWritten(verb: "add" | "edit", done: { name: string; personas: Persona[] }): string {
  return `${done.name} ${verb === "add" ? "written" : "changed"} · ${done.personas.length} persona(s)`;
}

export function personaDropped(done: { name: string; personas: Persona[] }): string {
  return `${done.name} dropped · ${done.personas.length} persona(s)`;
}

export function personaSwitched(done: { name: string; on: boolean }, agent: string): string {
  return `${done.name} ${done.on ? "on" : "off"} for ${agent}`;
}

export function generated(written: GeneratedPersonas & { saved: boolean }): string[] {
  const bill = written.evals === 0 ? "on your own judge key: not billed" : `${written.evals} eval(s) · $${written.cost_usd.toFixed(4)}`;
  return [
    ...written.personas.flatMap((one) => [`${one.name} · ${one.goal}`, `  ${one.style}`, ...one.expects.map((line) => `  expects: ${line}`)]),
    `${written.personas.length} caller(s) written · ${bill}${written.saved ? " · saved" : " · `--save` keeps them"}`,
  ];
}

export function pushedFiles(done: { pushed: string[] }, folder: string): string[] {
  return [...done.pushed.map((name) => `  ${name}`), `${done.pushed.length} persona(s) pushed from ${folder}`];
}

/** The end of a simulation: its call, the turns, the latencies, and every judge when judged. */
export function simulated(said: Simulated): string[] {
  const turns = said.callerTurns === null ? `${said.agentTurns} agent turn(s)` : `${said.callerTurns} caller turn(s) · ${said.agentTurns} agent turn(s) · ${said.line}`;
  const measured = latencyLine(said.medians);
  const lines = [`  ${said.call === "" ? "no call" : said.call} · ${turns}`, `  ${measured === "" ? "no metrics on this call" : measured}`];
  if (said.score !== null) lines.push(...callScore(said.score));
  if (said.unjudged) lines.push(`no call.score within a minute: read the call with \`pinecall sessions ${said.call}\`, or the console → Sessions`);
  return lines;
}

/** A replay: a header line, then one aligned line per check. */
export function replayed(answer: Replayed): string[] {
  const width = Math.max(...answer.verdicts.map((verdict) => verdict.check.length));
  return [`${answer.call}  ${answer.agent}`, ...answer.verdicts.map((verdict) => `  ${verdict.check.padEnd(width)}  ${verdict.status.padEnd(8)}  ${verdict.detail}`)];
}

/** How long ago, in the largest whole unit: 40s, 12m, 3h, 2d. */
export function ageOf(at: number, now: number): string {
  const seconds = Math.max(0, Math.floor(now - at));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86_400)}d`;
}

function brokeOf(one: EvalCase): string {
  return one.broke.length === 0 ? NOTHING : one.broke.map((broken) => broken.judge).join(", ");
}

// The commands a person types next, by where the case stands.
function nextForCase(one: EvalCase): string[] {
  const next: [string, string][] = [[`pinecall test --case ${one.name}`, "play it again through the agent this terminal serves"]];
  if (one.status === "pending") {
    next.push([`pinecall cases approve ${one.name}`, "the nightly plays it from now on"]);
    next.push([`pinecall cases dismiss ${one.name}`, "nothing to fix; --judge-was-wrong <judge> when the judge was"]);
  }
  if (one.status === "approved" && !one.kept_in_repo) next.push([`pinecall cases pull ${one.name}`, "a golden in the repository instead"]);
  if (one.status === "dismissed") next.push([`pinecall cases reopen ${one.name}`, "pending again"]);
  const wide = Math.max(...next.map(([command]) => command.length));
  return next.map(([command, why]) => `  ${command.padEnd(wide)}  ${why}`);
}

function driftRow(row: JudgeDrift, width: number): string {
  const delta = row.delta === null ? "     —" : `${row.delta >= 0 ? "+" : ""}${row.delta.toFixed(1)}`;
  const counted = (rate: Rate | null): string => (rate === null ? "nothing" : `${rate.held}/${rate.settled}`);
  const percent = (rate: Rate | null): string => (rate === null ? "—" : `${rate.percent.toFixed(1)}%`).padStart(6);
  return `  ${row.judge.padEnd(width)}  ${percent(row.before)} → ${percent(row.now)}  ${delta.padStart(6)} points  (${counted(row.now)} held, was ${counted(row.before)})`;
}

// Seconds in the largest whole unit.
function secondsAs(seconds: number): string {
  for (const [unit, size] of [["d", 86400], ["h", 3600], ["m", 60]] as const) if (seconds % size === 0) return `${seconds / size}${unit}`;
  return `${seconds}s`;
}

export { BROKEN, HELD };
