/** Evals as a terminal reads them: the matrix, progress, runs, cases and groups, personas, a simulation, a replay. */

import { HELD, BROKEN, callScore } from "../../judging/render.js";
import { clipped, count, date, formatHint, formatNotice, formatPairs, NEXT } from "../../kit/format.js";
import type { AgentValues, ComparisonRow } from "../../api/evals.js";
import type { Compared } from "../service/comparison.js";
import { table } from "../../kit/table.js";
import { type CaseGroup, type CaseList, type Drift, type EvalCase, type EvalRun, type GeneratedPersonas, type JudgeDrift, type Moved, type Persona, type Promoted, type Rate, type Replayed, type Saved, type Simulated } from "../service/index.js";
import { latencyLine } from "./matrix.js";

export { BottomBlock, header, progress, type Watched } from "./progress.js";
export { cellOf, latencyLine, matrix, suite } from "./matrix.js";

const NOTHING = "—";
// Max width of a persona's line in the list; `personas show` has it whole.
const ABOUT = 70;
export const NO_PERSONAS_YET = (agent: string): string => `${agent} has no personas yet: \`pinecall personas add <name> --goal '…' --style '…'\`, or the console's Personas`;

export const NO_RUNS = (agent: string | undefined): string => (agent === undefined ? "no run yet in this org: `pinecall test` makes one" : `${agent} has run no tests yet: \`pinecall test\` makes the first run · --all lists every agent's`);

/** The runs as a table, newest first: id, when, agent, status, how much held; then where the others are. */
export function runs(found: EvalRun[], agent?: string): string[] {
  if (found.length === 0) return formatNotice(NO_RUNS(agent));
  const rows = table(
    ["run", "when", "agent", "status", "held"],
    found.map((run) => {
      const cells = run.matrix?.runs.length ?? run.calls.length;
      const broken = new Set((run.matrix?.failures ?? []).map((one) => `${one.model} ${one.golden}`)).size;
      return [run.id, date(run.started_at), run.agent, run.status, `${cells - broken}/${cells}`];
    }),
  );
  return [...rows, formatHint("pinecall runs show <run> reads one", ...(agent === undefined ? [] : ["--all lists every agent's"]))];
}

export function moved({ before, after, moved: found }: { before: string; after: string; moved: Moved[] }): string[] {
  if (found.length === 0) return [`${before} → ${after}`, "  nothing moved"];
  return [`${before} → ${after}`, ...found.map((one) => `  ${one.golden}  ${one.metric}  ${one.was} → ${one.now}${one.reason === "" ? "" : `  ${one.reason}`}`)];
}

export function promoted(done: Promoted, fromSeq: number): string[] {
  const turns = done.candidate.turns.filter((turn) => turn.say !== undefined).length;
  return [`${done.path}  ${count(turns, "caller turn")} from seq ${fromSeq}`, ...done.notes.map((note) => `  ${note}`)];
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
    lines.push(`  the most recent broken ${count(new Set(found.broke.map((one) => one.call)).size, "call")}:`);
    for (const broke of found.broke) lines.push(`    ${broke.call}  ${broke.judge}  seq ${broke.seqs.join(", ")}  ${broke.reason}`);
  }
  return lines;
}

/** The inbox: how many wait, then one line a case — status, name, what broke, the env it came from, its age. */
export function cases(list: CaseList, status?: string, now = Date.now() / 1000): string[] {
  const waiting = `${list.agent} · ${count(list.pending, "case")} pending a decision, of ${list.pending_at_most} the inbox holds`;
  if (list.cases.length === 0 && status !== undefined) return [waiting, `${list.agent} has no ${status} case`];
  if (list.cases.length === 0) return [waiting, ...formatNotice(`${list.agent} has no cases here, a call a judge broke on is kept at hang-up: \`pinecall cases keep <call> --name x\` keeps one by hand`)];
  // One status everywhere is said once, in the head, and not on every row.
  const one = new Set(list.cases.map((each) => each.status)).size === 1;
  const rows = table(
    [...(one ? [] : ["status"]), "case", "broke", "env", "age"],
    list.cases.map((each) => [...(one ? [] : [each.status]), each.name, brokeOf(each), each.source_env, ageOf(each.created_at, now)]),
  );
  return [waiting, ...rows, formatHint("pinecall cases show <case> reads one", "approve", "dismiss")];
}

/** One case whole: what broke and why, its turns, the state, the expect, where it came from, and what to type next. */
export function oneCase(one: EvalCase): string[] {
  const golden = one.golden;
  const version = one.source_version === null ? "" : ` · settings v${one.source_version}`;
  const marks = [
    ...(one.held_out ? ["held out: played only when a run names it"] : []),
    ...(one.kept_in_repo ? ["kept in the repository: the nightly plays the file"] : []),
    ...(one.decided_by === null ? [] : [`${one.status} by ${one.decided_by}`]),
  ];
  const width = Math.max(0, ...one.broke.map((broken) => broken.judge.length));
  const opens: [string, string][] = [
    ["opens in", Object.keys(golden.state ?? {}).length === 0 ? "nothing set" : formatPairs(golden.state)],
    ...(golden.memory === undefined || golden.memory.length === 0 ? [] : [["memory", formatPairs(golden.memory)] as [string, string]]),
    ...(golden.today === undefined ? [] : [["today", golden.today] as [string, string]]),
    ["expects", Object.keys(golden.expect ?? {}).length === 0 ? "nothing" : formatPairs(golden.expect)],
  ];
  const label = Math.max(...opens.map(([name]) => name.length));
  return [
    `${one.name} · ${one.status} · ${one.agent}`,
    `  ${origin(one)}${version} · ${date(one.created_at)}`,
    ...marks.map((line) => `  ${line}`),
    "",
    "  broke",
    ...(one.broke.length === 0 ? [`    ${NOTHING} nothing: ${one.source === "person" ? "a person wrote it, no call made it" : "a person kept it from a call that held"}`] : one.broke.map((broken) => `    ${broken.judge.padEnd(width)}  ${broken.reason}`)),
    "  turns",
    ...golden.turns.flatMap((turn) => [`    ${turn.say === undefined ? `event ${turn.event?.name ?? ""} ${formatPairs(turn.event?.data ?? {})}` : `‹ ${turn.say}`}`, ...(turn.then ?? []).map((step) => `      then ${formatPairs(step)}`)]),
    ...opens.map(([name, said]) => `  ${name.padEnd(label)}  ${said}`),
    "",
    ...nextForCase(one),
  ];
}

/** One line per case written by hand: its name, whose, where it came from, where it stands, and whether only a run naming it plays it. */
export function casesAdded(added: EvalCase[]): string[] {
  return added.map((one) => `${one.name} · ${one.agent} · ${one.source ?? "person"} · ${one.status}${one.held_out ? " · held out" : ""}`);
}

export function caseKept(one: EvalCase): string[] {
  return [`${one.name} kept · ${one.status} · ${one.agent} · from ${one.source_call}`, `  expects  ${formatPairs(one.golden.expect ?? {})}`];
}

// Who keeps a case when a judge broke on its call: the runtime, at hang-up, and no person.
const AT_HANG_UP = "the hang-up panel";

// Where a case came from, its env, and the person who kept it when one did: a call, or a person's hand.
function origin(one: EvalCase): string {
  if (one.source === "person") return `written by ${one.author} by hand · ${one.source_env}`;
  return `from ${one.source_call} · ${one.source_env}${one.author === AT_HANG_UP ? " · kept at hang-up" : ` · kept by ${one.author}`}`;
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
  return [`${group.status.padEnd(9)} ${group.judge.padEnd(16)} ${count(group.cases, "call").padStart(9)}${sims}${fix}  ${group.id}`, `          ${group.cause}`];
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

export const APPLIED = ["applied as a new version of your settings", formatHint("pinecall test --case replays the group's calls on it")];

/** What to type next for a group, by what its proposal is. */
export function nextForGroup(one: CaseGroup): string[] {
  const proposal = one.proposal;
  if (proposal === undefined || proposal === null) return [formatHint(`pinecall cases propose ${one.id} asks the judge model for the cause and a fix`)];
  const fix = [`  ${proposal.cause}`, `  proposes ${proposal.kind} · ${proposal.where} · ${typeof proposal.change === "string" ? proposal.change : JSON.stringify(proposal.change)} · ${Math.round(proposal.confidence * 100)}% sure`];
  if (proposal.kind === "setting") return [...fix, formatHint(`pinecall cases apply ${one.id} writes it as a new version of your settings`)];
  if (proposal.kind === "code") return [...fix, formatHint("your assistant makes it: pinecall mcp, the cases tool, then pinecall test --case")];
  return fix;
}

/** Pinecall's first, then the agent's own (the class's, when it owns the roster); and a line when it has none of its own. */
export function personas(agent: string, found: Persona[]): string[] {
  const whose = (one: Persona): string => (one.owner === "pinecall" || one.owner === "class" ? one.owner : "yours");
  const about = (one: Persona): string => (one.owner === "pinecall" ? (one.summary ?? one.goal) : one.about || one.goal);
  const rows = table(["name", "owner", "on", "about"], found.map((one) => [one.name, whose(one), one.on ? "on" : "off", clipped(about(one), ABOUT)]));
  const lines = found.some((one) => one.owner !== "pinecall") ? rows : [...rows, ...formatNotice(NO_PERSONAS_YET(agent))];
  const steps = ["pinecall personas show <name> reads one", ...(found.some((one) => one.fixed === true) ? [`set in agents/${agent}/harness.* · personas({ on, own }) in the class`] : [])];
  return [...lines, formatHint(...steps)];
}

/** One persona whole, a label a line: what it is about, its goal and style, how it speaks, its facts, what it expects; a model only when not the runtime's. */
export function persona(one: Persona): string[] {
  const facts = Object.entries(one.facts);
  const acts = one.behavior;
  const behaving = [
    ...(acts.interrupts > 0 ? [`interrupts ${Math.round(acts.interrupts * 100)}% of the answers`] : []),
    ...(acts.pause_s > 0 ? [`pauses ${acts.pause_s} s before each line`] : []),
    ...(acts.backchannels > 0 ? [`murmurs into ${Math.round(acts.backchannels * 100)}% of the answers`] : []),
    ...(acts.speed === 1 ? [] : [`speaks at ${acts.speed}× the vendor's tempo`]),
    ...(acts.interferer_db === null ? [] : [`a ${acts.ambience} ${acts.interferer_db} dB under it`]),
    ...(acts.packet_loss > 0 ? [`${Math.round(acts.packet_loss * 100)}% packets lost`] : []),
  ];
  const models = [one.llm == null ? null : `played by ${one.llm}`, one.tts == null ? null : `read by ${one.tts}`, one.voice == null ? null : `voice ${one.voice}`].filter((said) => said !== null);
  const pairs: [string, string][] = [
    ...(one.about === "" ? [] : [["about", one.about] as [string, string]]),
    ["goal", one.goal],
    ["style", one.style],
    ...(behaving.length === 0 ? [] : [["spoken", behaving.join(" · ")] as [string, string]]),
    ...(models.length === 0 ? [] : [["models", models.join(" · ")] as [string, string]]),
    ["facts", facts.length === 0 ? "none: this caller may state nothing about themselves" : facts.map(([what, said]) => `${what} ${said}`).join(" · ")],
    ...(one.tags.length === 0 ? [] : [["tags", one.tags.join(", ")] as [string, string]]),
  ];
  const width = Math.max("expects".length, ...pairs.map(([label]) => label.length));
  const expects = one.expects.length === 0 ? ["nothing: the expected-outcome judge answers n/a on its calls"] : one.expects;
  return [
    `${one.name} · ${one.owner === "pinecall" ? `Pinecall's · ${one.on ? "on" : "off"}` : one.owner}`,
    ...pairs.map(([label, said]) => `  ${label.padEnd(width)}  ${said}`),
    ...expects.map((line, at) => `  ${(at === 0 ? "expects" : "").padEnd(width)}  ${line}`),
  ];
}

export function personaWritten(verb: "add" | "edit", done: { name: string; personas: Persona[] }): string {
  return `${done.name} ${verb === "add" ? "written" : "changed"} · ${count(done.personas.length, "persona")}`;
}

export function personaDropped(done: { name: string; personas: Persona[] }): string {
  return `${done.name} dropped · ${count(done.personas.length, "persona")}`;
}

export function personaSwitched(done: { name: string; on: boolean }, agent: string): string {
  return `${done.name} ${done.on ? "on" : "off"} for ${agent}`;
}

export function generated(written: GeneratedPersonas & Saved): string[] {
  const bill = written.evals === 0 ? "on your own judge key: not billed" : `${count(written.evals, "eval")} · $${written.cost_usd.toFixed(4)}`;
  const callers = written.personas.flatMap((one) => [`${one.name} · ${one.goal}`, `  ${one.style}`, ...one.expects.map((line, at) => `  ${at === 0 ? "expects" : "       "}  ${line}`)]);
  const head = `${count(written.personas.length, "caller")} · ${bill}`;
  if (written.written.length > 0) return [...callers, head, ...written.written.map((one) => `  written  ${one.path} · ${one.symbol}`), formatHint("add each to personas({ own }) in the class")];
  return [...callers, head, ...(written.saved ? ["  saved"] : [formatHint("--save keeps them")])];
}

/** The rows written as code, one line each: the file and the name the class imports. */
export function pulled(what: string, done: { written: { path: string; symbol: string }[] }): string[] {
  if (done.written.length === 0) return [`nothing to pull: the agent has no ${what} of its own as rows`];
  return [...done.written.map((one) => `${one.path}  ${one.symbol}`), `${done.written.length} ${what} written as code`, formatHint(`add them to ${what}({ own })`, `the rows stay until pinecall ${what} rm`)];
}
/** The end of a simulation: its call, the turns and the worst latency, and every judge when judged. */
export function simulated(said: Simulated): string[] {
  const turns = said.callerTurns === null ? count(said.agentTurns, "agent turn") : `${count(said.callerTurns, "caller turn")} · ${count(said.agentTurns, "agent turn")} · ${said.line}`;
  const measured = latencyLine(said.medians);
  const lines = [`${said.call === "" ? "no call" : said.call} · ${turns}${measured === "" ? "" : ` · ${measured}`}`];
  if (said.score !== null) lines.push(...callScore(said.score));
  if (said.unjudged) lines.push("no score within a minute", formatHint(`pinecall sessions ${said.call} reads it when the judges are done`));
  else if (said.call !== "") lines.push(formatHint(`pinecall sessions ${said.call} reads it whole`));
  return lines;
}

/** A replay: the call and agent, one aligned line per check, how many of each, then each next step the checks named, once. */
export function replayed(answer: Replayed): string[] {
  const width = Math.max(...answer.verdicts.map((verdict) => verdict.check.length));
  const steps: string[] = [];
  const rows = answer.verdicts.map((verdict) => {
    const [said = verdict.detail, step] = formatNotice(verdict.detail);
    if (step !== undefined && !steps.includes(step)) steps.push(step);
    return `  ${verdict.check.padEnd(width)}  ${verdict.status.padEnd(8)}  ${said}`;
  });
  const tally = new Map<string, number>();
  for (const verdict of answer.verdicts) tally.set(verdict.status, (tally.get(verdict.status) ?? 0) + 1);
  return [`${answer.call} · ${answer.agent}`, ...rows, [...tally].map(([status, n]) => `${n} ${status}`).join(" · "), ...steps];
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
  return next.map(([command, why]) => `  ${NEXT} ${command.padEnd(wide)}  ${why}`);
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

/** Seconds as the table says them: 1.24 s, 480 ms; nothing for a measure no turn took. */
function seconds(value: number | null): string {
  if (value === null) return "";
  return value >= 1 ? `${value.toFixed(2)} s` : `${String(Math.round(value * 1000))} ms`;
}

/** The agent's values in a few words: `thinks groq/openai/gpt-oss-120b · speaks deepgram`; its own settings when none. */
export function against(values: AgentValues): string {
  const pairs: [string, string | number | undefined][] = [["hears", values.stt], ["thinks", values.llm], ["speaks", values.tts], ["voice", values.voice], ["language", values.language], ["temperature", values.temperature], ["end of turn", values.end_of_turn]];
  const said = pairs.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`]));
  return said.length === 0 ? "the agent's own settings" : said.join(" · ");
}

/** The judges' column of one call: a call that ended in error reads so, whatever a judge made of what little it had. */
export function verdictOf(row: ComparisonRow): string {
  if (row.ended_at === null) return "on a call";
  if (row.why !== null) return "never started";
  if (row.end_reason === "error") return "ended in error";
  if (row.score === null) return (row.end_reason ?? "not judged").replace(/_/g, " ");
  return `${row.score.passed ? HELD : BROKEN} ${String(row.score.held)}/${String(row.score.judged)}`;
}

/** A comparison: the persona against the agent, one row per configuration best first, what was not placed, and how to read a call whole. */
export function comparison(done: Compared): string[] {
  const found = done.table;
  const lines = [`${found.persona} against ${found.agent} · ${count(found.rows.length, "call")} · best first`];
  lines.push(
    ...table(
      ["#", "the agent runs on", "judges", "reply", "thinks", "speaks", "hears", "cost", "length", "call"],
      found.rows.map((row, index) => [
        index + 1,
        against(row.against),
        verdictOf(row),
        seconds(row.latency.e2e_latency),
        seconds(row.latency.llm_node_ttft),
        seconds(row.latency.tts_node_ttfb),
        seconds(row.latency.transcription_delay),
        row.cost_usd === null ? "" : `$${row.cost_usd.toFixed(4)}`,
        row.ended_at === null ? "" : `${String(Math.round(row.ended_at - row.started_at))} s`,
        row.call,
      ]),
    ),
  );
  for (const row of found.rows) if (row.why !== null) lines.push(`never started, ${against(row.against)}: ${row.why}`);
  for (const one of done.refused) lines.push(`not placed, ${against(one.against)}: ${one.why}`);
  lines.push(formatHint("pinecall sessions <call> reads one whole"));
  return lines;
}
