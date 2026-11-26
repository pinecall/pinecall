/** A benchmark's numbers from its calls: each setup's share with its interval, replies, cost, hearing, judges, rounds, and the verdict against two bars. */

/** What a setup runs the agent on over its own settings: the test values a comparison's row carries. Nothing here is the agent's own. */
export interface AgentValues {
  stt?: string | undefined;
  llm?: string | undefined;
  tts?: string | undefined;
  realtime?: string | undefined;
  voice?: string | undefined;
  language?: string | undefined;
  temperature?: number | undefined;
  end_of_turn?: "stt" | "livekit" | "smart-turn" | undefined;
  smart_interruptions?: boolean | undefined;
}

/** The bars a setup is held to: the share of its counted calls completed, and its middle reply in seconds. */
export interface Bars {
  floor: number;
  ceiling_s: number;
}

/** Why a call is left out of every number: a vendor of the agent failed it, the platform lost it, or its own caller broke. */
export interface NotCounted {
  kind: "caller" | "platform" | "vendor";
  why: string;
}

/** One line of a call as the page plays it: who, what, and the second of the recording it begins at. */
export interface Line {
  who: "caller" | "agent" | "tool";
  text: string;
  at: number;
  until?: number;
  cut?: true;
  /** What a tool answered, shortened. */
  gave?: string;
}

/** One call of the benchmark, with everything the page shows of it. */
export interface BenchCall {
  call: string;
  comparison: string;
  caller: string;
  setup: string;
  /** The condition its line was under, when the benchmark has several. */
  condition?: string;
  /** The caller's nth call under its setup, from 1, in the order they started. */
  round: number;
  not_counted: NotCounted | null;
  /** Whether the caller got what it came for; null when nobody judged it. */
  completed: boolean | null;
  /** The judge's reason, the goal's first. */
  reason: string | null;
  ended: string | null;
  started_at: number;
  length_s: number | null;
  /** The call's own middle reply, and each reply it measured. */
  reply_s: number | null;
  replies_s: number[];
  slowest_reply_s: number | null;
  cost_usd: number | null;
  /** Models the gateway priced nothing for: the call's cost is not its whole cost. */
  unpriced: string[];
  stages: { llm_ttft: number | null; tts_ttfb: number | null; transcription_delay: number | null; end_of_turn_delay: number | null };
  judges: { name: string; verdict: string; reason: string }[];
  hearing: Record<string, number | null> | null;
  /** The recording beside the page, when the gateway kept one. */
  recording: string | null;
  /** False when the gateway did not say when the recording began and the lines' times were placed by the log alone. */
  timed: boolean;
  lines: Line[];
}

/** A share of calls with the 95% interval around it. */
export interface Share {
  completed: number;
  of: number;
  share: number | null;
  /** Wilson's interval at 95%: where the true share plausibly sits after this many calls. */
  low: number | null;
  high: number | null;
}

/** One configuration of the agent and everything measured of it. */
export interface Setup {
  name: string;
  values: AgentValues;
  kind: "pipeline" | "speech to speech" | "own settings";
  calls: number;
  completed: Share;
  reply: { p50: number | null; p90: number | null; slowest: number | null };
  cost: { total: number; per_call: number | null; per_completed: number | null; unpriced: string[] };
  length_s: number | null;
  stages: BenchCall["stages"];
  hearing: { calls: number; lines: number; unanswered: number; phantom_turns: number; cut_by_the_room: number; cut_by_a_murmur: number; talked_over: number; word_error_rate: number | null } | null;
  judges: { name: string; held: number; broken: number; other: number }[];
  by_caller: (Share & { caller: string; every: boolean })[];
  rounds: { round: number; completed: number; of: number }[];
  /** The lowest and highest share a round completed: how far one run of the callers moves from another. */
  spread: { least: number; most: number } | null;
  clears: { floor: boolean | null; ceiling: boolean | null };
  not_counted: number;
  /** More of its calls were left out than counted: what is left is too little to hold it to a bar. */
  thin: boolean;
  /** Against an earlier report, when one was given. */
  baseline?: Moved;
  /** Its numbers under each condition, the baseline's first, when the benchmark has several: everything above is the baseline's. */
  under?: Under[];
}

/** A number a condition moved, a call: what it was on the baseline's line and what it is under this one. */
export interface Shift {
  what: string;
  was: number;
  now: number;
}

/** A setup under one condition: what it completed there, how it heard its callers, and how that moved against the baseline's line. */
export interface Under {
  condition: string;
  calls: number;
  not_counted: number;
  thin: boolean;
  completed: Share;
  reply: Setup["reply"];
  length_s: number | null;
  hearing: Setup["hearing"];
  rounds: Setup["rounds"];
  clears: Setup["clears"];
  /** Against the baseline's line; null for the baseline itself. `most` is what moved by a step or more (a turn a call, a second of reply, two minutes of a call, a quarter of the words), the most steps first, two at most. */
  moved: (Moved & { most: Shift[] }) | null;
}

/** How a setup moved against an earlier report of it. */
export interface Moved {
  share_was: number | null;
  reply_was: number | null;
  per_completed_was: number | null;
  share_change: number | null;
  reply_change: number | null;
  /** The share fell by more than the earlier report's own rounds moved among themselves. */
  regressed: boolean;
}

/** What the benchmark comes to. */
export interface Verdict {
  /** Whether any setup cleared both bars; null when nobody judged a call. */
  passed: boolean | null;
  cleared: string[];
  /** The cheapest per completed call of the setups that cleared both, where a cost was measured; else the one that completed the most. */
  winner: string | null;
  says: string;
  /** With several conditions: the setups that clear both bars under every one of them. */
  held_under_every?: string[];
}

const Z = 1.959964;

/** The agent's values in a few words, as the comparison's table says them. */
export function nameOf(values: AgentValues): string {
  const pairs: [string, string | number | undefined][] = [["talks", values.realtime], ["hears", values.stt], ["thinks", values.llm], ["speaks", values.tts], ["voice", values.voice], ["language", values.language], ["temperature", values.temperature], ["end of turn", values.end_of_turn], ["smart interruptions", values.smart_interruptions === undefined ? undefined : values.smart_interruptions ? "on" : "off"]];
  const said = pairs.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`]));
  return said.length === 0 ? "the agent's own settings" : said.join(" · ");
}

function kindOf(values: AgentValues): Setup["kind"] {
  if (values.realtime !== undefined) return "speech to speech";
  return Object.keys(values).length === 0 ? "own settings" : "pipeline";
}

/** The value a share of the sorted measures sits under; none of no measures. */
export function percentile(values: readonly number[], share: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((one, other) => one - other);
  const at = (sorted.length - 1) * share;
  const under = Math.floor(at);
  const over = Math.ceil(at);
  return (sorted[under] ?? 0) + ((sorted[over] ?? 0) - (sorted[under] ?? 0)) * (at - under);
}

/** A share with Wilson's 95% interval: honest for a handful of calls, where a plain percentage is not. */
export function shareOf(completed: number, of: number): Share {
  if (of === 0) return { completed, of, share: null, low: null, high: null };
  const p = completed / of;
  const middle = (p + (Z * Z) / (2 * of)) / (1 + (Z * Z) / of);
  const half = (Z * Math.sqrt((p * (1 - p)) / of + (Z * Z) / (4 * of * of))) / (1 + (Z * Z) / of);
  return { completed, of, share: p, low: Math.max(0, middle - half), high: Math.min(1, middle + half) };
}

const measured = (values: readonly (number | null)[]): number[] => values.filter((value): value is number => value !== null);
const sum = (values: readonly number[]): number => values.reduce((total, value) => total + value, 0);

function hearingOf(calls: readonly BenchCall[]): Setup["hearing"] {
  const heard = calls.filter((call) => call.hearing !== null);
  if (heard.length === 0) return null;
  const total = (name: string): number => sum(heard.map((call) => call.hearing?.[name] ?? 0));
  return {
    calls: heard.length,
    lines: total("lines"),
    unanswered: total("unanswered"),
    phantom_turns: total("phantom_turns"),
    cut_by_the_room: total("cut_by_the_room"),
    cut_by_a_murmur: total("cut_by_a_murmur"),
    talked_over: total("talked_over"),
    word_error_rate: percentile(measured(heard.map((call) => call.hearing?.["word_error_rate"] ?? null)), 0.5),
  };
}

function judgesOf(calls: readonly BenchCall[]): Setup["judges"] {
  const named = new Map<string, { held: number; broken: number; other: number }>();
  for (const call of calls) {
    for (const judge of call.judges) {
      const one = named.get(judge.name) ?? { held: 0, broken: 0, other: 0 };
      if (judge.verdict === "held") one.held += 1;
      else if (judge.verdict === "broken") one.broken += 1;
      else one.other += 1;
      named.set(judge.name, one);
    }
  }
  return [...named].map(([name, one]) => ({ name, ...one }));
}

/** One setup's numbers from its calls; a call that does not count is in none of them. */
export function setupOf(values: AgentValues, all: readonly BenchCall[], callers: readonly string[], bars: Bars): Setup {
  const counted = all.filter((call) => call.not_counted === null);
  const judged = counted.filter((call) => call.completed !== null);
  const done = judged.filter((call) => call.completed === true);
  const completed = shareOf(done.length, judged.length);
  const p50 = percentile(measured(counted.map((call) => call.reply_s)), 0.5);
  const total = sum(measured(counted.map((call) => call.cost_usd)));
  const roundsSeen = [...new Set(judged.map((call) => call.round))].sort((one, other) => one - other);
  const rounds = roundsSeen.map((round) => {
    const its = judged.filter((call) => call.round === round);
    return { round, completed: its.filter((call) => call.completed === true).length, of: its.length };
  });
  const shares = rounds.map((round) => round.completed / round.of);
  const stage = (name: keyof BenchCall["stages"]): number | null => percentile(measured(counted.map((call) => call.stages[name])), 0.5);
  return {
    name: nameOf(values),
    values,
    kind: kindOf(values),
    calls: counted.length,
    completed,
    reply: { p50, p90: percentile(counted.flatMap((call) => call.replies_s), 0.9), slowest: measured(counted.map((call) => call.slowest_reply_s)).reduce<number | null>((most, value) => (most === null || value > most ? value : most), null) },
    cost: { total, per_call: counted.length === 0 ? null : total / counted.length, per_completed: done.length === 0 ? null : total / done.length, unpriced: [...new Set(counted.flatMap((call) => call.unpriced))] },
    length_s: percentile(measured(counted.map((call) => call.length_s)), 0.5),
    stages: { llm_ttft: stage("llm_ttft"), tts_ttfb: stage("tts_ttfb"), transcription_delay: stage("transcription_delay"), end_of_turn_delay: stage("end_of_turn_delay") },
    hearing: hearingOf(counted),
    judges: judgesOf(counted),
    by_caller: callers.map((caller) => {
      const its = judged.filter((call) => call.caller === caller);
      const share = shareOf(its.filter((call) => call.completed === true).length, its.length);
      return { caller, ...share, every: share.of > 0 && share.completed === share.of };
    }),
    rounds,
    spread: shares.length < 2 ? null : { least: Math.min(...shares), most: Math.max(...shares) },
    clears: { floor: completed.share === null ? null : completed.share >= bars.floor, ceiling: p50 === null ? null : p50 <= bars.ceiling_s },
    not_counted: all.length - counted.length,
    thin: all.length - counted.length > counted.length,
  };
}

/** The order a benchmark lists its setups in: one that lost most of its calls last, then the larger share completed, then the faster reply. */
export function byStanding(one: Setup, other: Setup): number {
  return Number(one.thin) - Number(other.thin) || (other.completed.share ?? -1) - (one.completed.share ?? -1) || (one.reply.p50 ?? Infinity) - (other.reply.p50 ?? Infinity);
}

/** Whether a setup's cost is a cost: something was charged and no model went unpriced. */
function priced(setup: Setup): boolean {
  return setup.cost.per_completed !== null && setup.cost.total > 0 && setup.cost.unpriced.length === 0;
}

// A bar nothing was measured against (a written call has no reply time) fails nobody; a floor nobody
// judged is no pass, since "nobody looked" must never read as one.
/** The verdict: which setups clear both bars, and which of them to take. */
export function verdictOf(setups: readonly Setup[], bars: Bars): Verdict {
  if (setups.every((setup) => setup.clears.floor === null)) return { passed: null, cleared: [], winner: null, says: "nobody judged a call: run it with --judge and a caller that expects something" };
  // A setup that lost most of its calls is held to no bar: on 2026-11-26 a model whose vendor refused
  // fourteen of its twenty read "6 of 6, clears both" and was listed first.
  const thin = setups.filter((setup) => setup.thin);
  const lost = thin.length === 0 ? "" : `; ${thin.map((setup) => setup.name).join(", ")} lost most of ${thin.length === 1 ? "its" : "their"} calls and ${thin.length === 1 ? "is" : "are"} held to no bar`;
  const cleared = setups.filter((setup) => !setup.thin && setup.clears.floor === true && setup.clears.ceiling !== false);
  const floor = `${String(Math.round(bars.floor * 100))}% of calls completed`;
  const ceiling = `a reply within ${String(bars.ceiling_s)} s`;
  if (cleared.length === 0) return { passed: false, cleared: [], winner: null, says: setups.length === 1 ? `it does not clear both bars: ${floor}, ${ceiling}${lost}` : `no setup clears both bars: ${floor}, ${ceiling}${lost}` };
  const cheapest = cleared.filter(priced).sort((one, other) => (one.cost.per_completed ?? 0) - (other.cost.per_completed ?? 0))[0];
  const best = [...cleared].sort((one, other) => (other.completed.share ?? 0) - (one.completed.share ?? 0) || (one.reply.p50 ?? Infinity) - (other.reply.p50 ?? Infinity))[0];
  const winner = cheapest ?? best;
  const names = cleared.map((setup) => setup.name);
  if (setups.length === 1) return { passed: true, cleared: names, winner: winner?.name ?? null, says: `it clears both bars: ${floor}, ${ceiling}${lost}` };
  const how = cheapest === undefined ? "the one that completed the most (no cost was measured for them)" : "the cheapest per completed call";
  return { passed: true, cleared: names, winner: winner?.name ?? null, says: `${String(cleared.length)} of ${String(setups.length)} setups clear both bars; ${winner?.name ?? ""} is ${how}${lost}` };
}

/** What an earlier report said of a setup: enough to say how it moved. */
export interface Earlier {
  name: string;
  completed: { share: number | null };
  reply: { p50: number | null };
  cost: { per_completed: number | null };
  spread: { least: number; most: number } | null;
}

// A share moves from one run of the same callers to the next with nothing changed: a fall is a
// regression only when it is larger than the earlier report's own rounds moved among themselves.
/** How a setup moved against the earlier report's setup of the same name. */
export function movedSince(now: Setup, was: Earlier): Moved {
  const change = now.completed.share === null || was.completed.share === null ? null : now.completed.share - was.completed.share;
  const moved = was.spread === null ? 0 : was.spread.most - was.spread.least;
  return {
    share_was: was.completed.share,
    reply_was: was.reply.p50,
    per_completed_was: was.cost.per_completed,
    share_change: change,
    reply_change: now.reply.p50 === null || was.reply.p50 === null ? null : now.reply.p50 - was.reply.p50,
    regressed: change !== null && -change > moved + 1e-9,
  };
}
