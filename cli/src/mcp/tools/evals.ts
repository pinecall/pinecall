/** The `test`, `runs`, `eval`, `cases`, `simulate` and `personas` tools: the evals domain, over its service. */

import { join } from "node:path";

import { z } from "zod";

import * as service from "../../evals/service/index.js";
import { tool, ToolRefused, type ToolContext } from "../tool.js";
import { AGENT, needed, WAIT, WAIT_S } from "./fields.js";

const DAY_S = 86_400;

/** Something long a tool started and a later call of it waits for: its answer, and what it has said so far. */
export interface InFlight {
  pending: Promise<unknown>;
  soFar(): unknown;
}

export const test = tool({
  name: "test",
  description: "Run the agent's goldens through the agent wherever it is held, under every model named, written or said out loud; waits for the matrix.",
  schema: {
    action: z.enum(["run", "wait"]).describe("run starts the goldens and waits up to wait_s; wait keeps waiting for the run in flight"),
    agent: AGENT,
    grep: z.string().optional().describe("only goldens whose name holds this"),
    models: z.array(z.string()).optional().describe("a column per model: vendor/model, a model, or a tier (haiku); the agent's own when left out"),
    voice: z.boolean().optional().describe("say the goldens out loud on a real line (the files alone: cases are played written)"),
    background_noise: z.number().optional().describe("spoken runs: dB under the caller of what plays behind them"),
    ambience: z.enum(service.AMBIENCES).optional().describe("spoken runs: what plays behind the caller"),
    packet_loss: z.number().min(0).max(1).optional().describe("spoken runs: the share of the caller's packets lost, 0 to 1"),
    files: z.boolean().optional().describe("the golden files alone, without the dataset; nothing said plays the files and every approved case both, as `pinecall test` does"),
    case: z.array(z.string().min(1)).optional().describe("cases of the org's dataset to play, by name, whatever their status (`cases` lists them); with `case` or `dataset`, only the cases are played, not the goldens"),
    dataset: z.boolean().optional().describe("play every case a person approved, not held out and not kept in the repository: the nightly"),
    version: z.number().int().min(1).optional().describe("play every call on this version of the agent's settings instead of the one standing"),
    wait_s: WAIT,
  },
  manual:
    "`test run` runs the goldens in `agents/<agent>/test/goldens/` through the agent — the copy `start` holds when it holds it in the env asked, else whoever holds it there, with nothing started — the gateway driving and scoring each conversation, a column per model in `models`. It answers the matrix once done — every golden held or broken, with the evidence, each call's latency, and a reproduction written under `.pinecall/evals/` for each that broke — or, past `wait_s`, the run's id: call `test wait` to keep waiting. One run per agent at a time. A spoken run (`voice`) plays the golden files alone — cases are real callers' words, played written — and can add noise and packet loss. `case` names cases of the org's dataset to play instead of the goldens — a pending one too, which reproduces the call that broke — and `dataset` plays every approved one; cases play in the sandbox only. `version` runs every call on that version of the agent's settings. The run plays on the key's corner: a person's own in the sandbox, where CI's server token plays on the team's.",
  handler: async (args, ctx) => {
    const reached = await ctx.session.reach(ctx, args.agent);
    const going = ctx.session.runs.get(reached.slug);
    if (args.action === "wait") {
      if (going === undefined) throw new ToolRefused(`no run of ${reached.slug} in flight: call test with action run`);
      return await waited(ctx.session.runs, reached.slug, going, args.wait_s ?? WAIT_S);
    }
    if (going !== undefined) throw new ToolRefused(`a run of ${reached.slug} is in flight: call test with action wait for it`);
    const input = service.SuiteInput.parse({
      ...service.whatPlays({ files: args.files, dataset: args.dataset, cases: args.case, paths: false, voice: args.voice }),
      voice: args.voice === true,
      backgroundNoise: args.background_noise,
      ambience: args.ambience,
      packetLoss: args.packet_loss,
      models: args.models ?? [],
      cases: args.case,
      version: args.version,
    });
    const home = ctx.agent("test", { agent: reached.slug });
    // The files play unless only the cases were asked for, as `pinecall test` decides it.
    const goldens = input.files ? service.matching(await service.goldensIn([home.goldens]), args.grep) : [];
    if (goldens.length === 0 && !service.playsCases(input)) throw new ToolRefused(`no golden${args.grep === undefined ? "" : ` matching ${args.grep}`} in ${home.goldens}`);
    let id: string | null = null;
    const pending = service.runSuite(ctx, reached.slug, goldens, input, reached.app, { onStarted: (started) => (id = started) }).then((report) => ({ ...report, env: ctx.env }));
    const started: InFlight = { pending, soFar: () => ({ status: "running", run: id, says: "call test with action wait to keep waiting, or runs show with this id" }) };
    ctx.session.runs.set(reached.slug, started);
    return await waited(ctx.session.runs, reached.slug, started, args.wait_s ?? WAIT_S);
  },
});

export const runs = tool({
  name: "runs",
  description: "The suites the gateway kept: the newest, one run's matrix, what moved between two, a real call written as a golden candidate, and each judge's drift.",
  schema: {
    action: z.enum(["list", "show", "diff", "promote", "drift"]).describe("list the newest runs; show one; diff two; promote a real call to a golden candidate; drift compares each judge's held-rate over two windows"),
    agent: AGENT,
    run: z.string().optional().describe("`show`: the run's id"),
    before: z.string().optional().describe("`diff`: the earlier run"),
    after: z.string().optional().describe("`diff`: the later run"),
    call: z.string().optional().describe("`promote`: the call to write as a golden candidate"),
    name: z.string().optional().describe("`promote`: the candidate's file name"),
    window_days: z.number().min(1).optional().describe("`drift`: the recent window, 7 days when left out"),
    baseline_days: z.number().min(1).optional().describe("`drift`: the days before it compared against, 30 when left out; longer than the window"),
    threshold: z.number().min(0).optional().describe("`drift`: the drop in points that counts, 10 when left out"),
  },
  manual:
    "`runs list` and `show` read the suites the gateway kept; `diff` says which goldens moved between two runs. `promote` writes the golden the gateway derives from one real call as a candidate under the agent's `agents/<agent>/test/candidates/`: meant for a call that broke, whose expect says what must not happen again — a call that held gives an empty expect, and you write what it must keep doing. Read it before you keep it. `drift` compares each judge's held-rate in the last week with the month before it and names the judges past the threshold.",
  handler: async (args, ctx) => {
    if (args.action === "show") return await service.getRun(ctx, needed(args.run, "run"));
    if (args.action === "diff") return await service.diffRuns(ctx, needed(args.before, "before"), needed(args.after, "after"));
    if (args.action === "promote") return await service.promoteCall(ctx, service.PromoteInput.parse({ call: needed(args.call, "call"), name: args.name, out: ctx.agent("runs", { agent: args.agent }).candidates }));
    const agent = ctx.slug("runs", { agent: args.agent });
    if (args.action === "list") return { runs: (await service.listRuns(ctx, 20, agent)).map((run) => ({ id: run.id, status: run.status, failures: run.matrix?.failures.length ?? null, started_at: run.started_at, finished_at: run.finished_at })) };
    return await service.driftOf(ctx, service.DriftInput.parse({ agent, window: (args.window_days ?? 7) * DAY_S, baseline: (args.baseline_days ?? 30) * DAY_S, threshold: args.threshold }));
  },
});

export const evalTool = tool({
  name: "eval",
  description: "Check one finished call again by code: consent, banned words, errors, latency, talk share, interruptions — held, broken, deferred or skipped.",
  schema: {
    call: z.string().describe("the call's id"),
    banned: z.array(z.string()).optional().describe("words the agent must not say"),
    budget: z.record(z.string(), z.number()).optional().describe("seconds per latency (e2e_latency, llm_node_ttft, tts_node_ttfb), talk_share 0..1; replaces the defaults whole"),
  },
  manual: "`eval` rebuilds one finished call from its log and runs the six code checks on it, no model asked. A `budget` replaces the default latencies whole, so name every key you want checked.",
  handler: async (args, ctx) => await service.replayCall(ctx, args.call, { ...(args.banned === undefined ? {} : { banned: args.banned }), ...(args.budget === undefined ? {} : { budget: args.budget }) }),
});

export const cases = tool({
  name: "cases",
  description: "The org's dataset: real calls and simulations kept as cases, grouped by the judge that broke them — a group diagnosed with a fix proposed, a setting applied, a persona made from it, decided whole — and each case read, approved, dismissed, pulled into the repository, a call kept, a golden written by hand added.",
  schema: {
    action: z.enum(["groups", "group", "propose", "apply", "persona", "list", "show", "approve", "dismiss", "reopen", "pull", "keep", "add"]).describe("groups lists the agent's case groups; group shows one whole; propose diagnoses one (cause + fix); apply writes its proposed setting; persona keeps a caller like its calls'; list the agent's cases, the pending first; show one whole; approve or dismiss a case or a whole group (`name` a grp_ id); reopen a case; pull its golden into the repository; keep a finished call as a case; add a golden written by hand as an approved case"),
    agent: AGENT,
    name: z.string().min(1).optional().describe("the case's name within the agent, or a group's id (grp_…); `keep` and `add`: the name the new case is played by (`add`: the golden's own when it has one)"),
    status: z.enum(service.STATUSES).optional().describe("`list`: only the cases in this status; every status when left out"),
    call: z.string().min(1).optional().describe("`keep`: the finished call to keep as an approved case"),
    golden: z.record(z.string(), z.unknown()).optional().describe("`add`: the golden itself as JSON — {name?, turns: [{say, then?}…], expect?, memory?, today?} — never a file's path"),
    held_out: z.boolean().optional().describe("`keep` and `add`: played only when a run names it, never by the nightly"),
    judge_was_wrong: z.string().min(1).optional().describe("`dismiss`: the judge that broke and should have held, kept as a calibration label; for a group, any value says its judge was wrong"),
    note: z.string().optional().describe("`dismiss`: why, kept on that label; only beside judge_was_wrong"),
  },
  manual:
    "`cases` is the dataset real calls make, and the loop that fixes the agent. A call a judge broke on — a simulation's too — is kept at hang-up as a pending case and joins its agent's GROUP for that judge (`groups`, `group` with the grp_ id). `propose` asks the judge model for the cause the calls share and the smallest fix, as `proposal`: {cause, kind, where, change, confidence}. Act on it by kind: `setting` — tell the person the setting and the value, and on their yes call `apply` (a new settings version), then `test` with `case` to replay; `code` — `where` names the tool or prompt block and `change` what it must do: open that file in the project, make the change, run `test` with `case` until it holds, then `approve` the group and offer a pull request; `knowledge` — propose the text to add to the agent's knowledge base; `none` — the calls show no fault of the agent's: offer `dismiss` with `judge_was_wrong`. Never approve or apply without the person. `persona` keeps a caller like the group's for the nightly. A single case: `list`, `show`, `approve`, `dismiss`, `reopen`, `pull` (its golden into `agents/<agent>/test/goldens/`), `keep` (a finished call). `add` keeps a golden written by hand — given whole as `golden`, never read from the person's disk — as an approved case under its name (`source: person`); the same name again rewrites it, and a name a call made is the gateway's 409. A case names only words, what the caller says and what the agent must say or never say; a golden that names a state or a tool belongs beside the code, in `agents/<agent>/test/goldens/`. Forgetting one cannot be undone, so it is never a tool: `pinecall cases forget` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "keep") return await service.keepCall(ctx, service.KeepInput.parse({ call: needed(args.call, "call"), name: needed(args.name, "name"), heldOut: args.held_out === true }));
    const agent = ctx.slug("cases", { agent: args.agent });
    if (args.action === "add") {
      if (args.golden === undefined) throw new ToolRefused("add takes the golden itself, as JSON");
      const written = args.golden as service.WrittenGolden;
      const name = written.name ?? needed(args.name, "name");
      return await service.keepGolden(ctx, agent, { ...written, name }, args.held_out === true);
    }
    if (args.action === "groups") return { groups: await service.listGroups(ctx, agent) };
    if (args.action === "list") return await service.listCases(ctx, agent, args.status);
    const name = needed(args.name, "name");
    if (args.action === "group" || (args.action === "show" && service.isGroup(name))) return await service.getGroup(ctx, name);
    if (args.action === "propose") return await service.proposeFix(ctx, name);
    if (args.action === "apply") return await service.applyFix(ctx, name);
    if (args.action === "persona") return await service.personaOfGroup(ctx, name);
    if (service.isGroup(name) && (args.action === "approve" || args.action === "dismiss")) {
      return await service.decideGroup(ctx, name, args.action === "approve", { judgeWasWrong: args.judge_was_wrong !== undefined, note: args.note });
    }
    if (args.action === "show") return await service.getCase(ctx, agent, name);
    if (args.action === "approve") return await service.approveCase(ctx, agent, name);
    if (args.action === "reopen") return await service.reopenCase(ctx, agent, name);
    if (args.action === "pull") {
      const home = ctx.agent("cases", { agent: args.agent });
      return await service.pullCase(ctx, home.name, name, home.goldens);
    }
    return await service.dismissCase(ctx, agent, name, service.DismissInput.parse({ judgeWasWrong: args.judge_was_wrong, note: args.note }));
  },
});

export const simulate = tool({
  name: "simulate",
  description: "A model plays one of the agent's personas against the agent wherever it is held, written or spoken, and the call is judged at hang-up.",
  schema: {
    action: z.enum(["run", "wait"]).describe("run starts a simulated call and waits up to wait_s; wait keeps waiting for the one in flight"),
    persona: z.string().optional().describe("`run`: the persona's name, from `personas`"),
    agent: AGENT,
    turns: z.number().int().min(1).max(40).optional().describe("how many turns the caller improvises; 15 when left out"),
    voice: z.boolean().optional().describe("a spoken call on a real line, the caller in a voice of its own"),
    background_noise: z.number().optional().describe("spoken calls: dB under the caller of what plays behind them"),
    ambience: z.enum(service.AMBIENCES).optional().describe("spoken calls: what plays behind the caller; the persona's own when left out"),
    packet_loss: z.number().min(0).max(1).optional().describe("spoken calls: the share of the caller's packets lost, 0 to 1"),
    llm: z.string().optional().describe("the model that plays the caller this run (vendor/model); the persona's when left out"),
    tts: z.string().optional().describe("the vendor the caller's voice is read by this run; the persona's when left out"),
    caller_voice: z.string().optional().describe("the caller's voice this run, one of that vendor's (`voices`)"),
    wait_s: WAIT,
  },
  manual:
    "`simulate run` runs one call a model improvises as the persona — its goal, its manner, its facts, no script — against the agent: the copy `start` holds when it holds it in the env asked, else whoever holds it there, with nothing started. It answers the conversation and every judge's verdict: the platform's own, the persona's rule for hanging up satisfied, and your own judges. A call of fifteen turns outlasts `wait_s`: then it answers the transcript so far, and `simulate wait` picks it up. One simulation per agent at a time. `llm`, `tts` and `caller_voice` play the caller on another model or voice for this run alone; the persona keeps its own. The caller runs on the runtime's keys unless the org brought that vendor's; each run counts as one simulation, and what its caller cost is kept with the call.",
  handler: async (args, ctx) => {
    const reached = await ctx.session.reach(ctx, args.agent);
    const going = ctx.session.simulations.get(reached.slug);
    if (args.action === "wait") {
      if (going === undefined) throw new ToolRefused(`no simulation of ${reached.slug} in flight: call simulate with action run`);
      return await waited(ctx.session.simulations, reached.slug, going, args.wait_s ?? WAIT_S);
    }
    if (going !== undefined) throw new ToolRefused(`a simulation of ${reached.slug} is in flight: call simulate with action wait for it`);
    const persona = await service.getPersona(ctx, reached.slug, needed(args.persona, "persona"));
    const voice = args.voice === true;
    const input = service.SimulateInput.parse({
      persona: persona.name,
      judge: true,
      voice,
      turns: args.turns,
      llm: args.llm,
      tts: args.tts,
      callerVoice: args.caller_voice,
      ...(voice ? { backgroundNoise: args.background_noise, ambience: args.ambience, packetLoss: args.packet_loss } : {}),
    });
    const transcript: string[] = [];
    const pending = service
      .simulate(ctx, { slug: reached.slug, app: () => reached.app }, persona, input, { onEntry: (entry) => transcriptLine(transcript, entry) })
      .then((said) => ({ call: said.call, transcript, score: said.score, medians: said.medians, env: ctx.env }));
    const started: InFlight = { pending, soFar: () => ({ status: "running", transcript_so_far: [...transcript], says: "call simulate with action wait to keep waiting" }) };
    ctx.session.simulations.set(reached.slug, started);
    return await waited(ctx.session.simulations, reached.slug, started, args.wait_s ?? WAIT_S);
  },
});

export const personas = tool({
  name: "personas",
  description: "The agent's simulated callers: Pinecall's library switched on or off, its own written (a goal, a manner, facts, what it expects of the agent, how it acts on a line), callers generated from the agent, dropped.",
  schema: {
    action: z.enum(["list", "show", "add", "edit", "rm", "on", "off", "generate"]).describe("list Pinecall's personas then the agent's own; show one; add one; edit one (only the fields named change); rm one of the agent's own; on/off one of Pinecall's; generate callers written from the agent"),
    agent: AGENT,
    name: z.string().optional().describe("the persona's name: lowercase letters, digits and dashes"),
    goal: z.string().optional().describe("what the caller wants, in the first person"),
    style: z.string().optional().describe("how they talk"),
    about: z.string().optional().describe("who they are, in a line; `generate`: what the callers are about"),
    facts: z.record(z.string(), z.string()).optional().describe("what they know and say when asked: their name, an order number…"),
    expects: z.array(z.string()).optional().describe("what the agent should do, one line each (\"The agent should …\"): the expected-outcome judge holds every call of theirs to them; the caller is never told"),
    tags: z.array(z.string()).optional().describe("words to find the caller by: realism, red-team, pricing…"),
    interrupts: z.number().min(0).max(1).optional().describe("on a spoken call, the share of the agent's answers they talk over"),
    pause_s: z.number().min(0).max(10).optional().describe("on a spoken call, seconds of silence before each line"),
    backchannels: z.number().min(0).max(1).optional().describe("on a spoken call, the share of the agent's answers they murmur an \"mm-hmm\" into, keeping their turn"),
    speed: z.number().min(0.5).max(2).optional().describe("how fast they speak: 1 as the voice's vendor reads it, 0.8 slower, 1.3 faster"),
    ambience: z.enum(service.AMBIENCES).optional().describe("what plays behind them on a spoken call, at background_noise dB under them"),
    background_noise: z.number().nullable().optional().describe("dB under the caller the ambience plays at; null for a quiet room"),
    llm: z.string().optional().describe("the model that plays them; the runtime's when left out"),
    tts: z.string().optional().describe("the vendor their voice is read by; the runtime's when left out: a voice the agent does not have"),
    voice: z.string().optional().describe("their voice on a spoken call, one of that vendor's (`voices`)"),
    rename: z.string().optional().describe("`edit`: a new name"),
    n: z.number().int().min(1).max(10).optional().describe("`generate`: how many callers, 3 unless said"),
    from_call: z.string().optional().describe("`generate`: callers like this finished call's caller"),
    template: z.string().optional().describe("`generate`: callers like one of Pinecall's, by name"),
    save: z.boolean().optional().describe("`generate`: keep every caller written as the agent's own"),
  },
  manual:
    "`personas` keeps the callers a model plays against the agent. Pinecall's library comes first — realism (in-a-hurry, wrong-number, interrupts, elderly-slow…) and a red team (prompt-leak, data-leak, harmful…) — each off until `on`; the nightly plays what is on. The agent's own are a goal, a manner, facts, and `expects`: what the agent should do, one verifiable line each, judged at hang-up and never told to the caller. `interrupts` and `pause_s` make a spoken caller talk over the agent and hesitate, so barge-in is tested for real; `backchannels` has it murmur an mm-hmm while the agent speaks, `speed` slows or hurries its voice, and `ambience` with `background_noise` puts a television, a café, an office or a street behind it. `generate` writes callers from the agent's prompt, tools and knowledge (one eval each, none on the org's own judge key); show them to the person and `save` the ones they keep. `simulate` runs one.",
  handler: async (args, ctx) => {
    const agent = ctx.agent("personas", { agent: args.agent }).name;
    if (args.action === "list") return { personas: await service.listPersonas(ctx, agent) };
    if (args.action === "generate") return await service.generatePersonas(ctx, agent, service.GenerateInput.parse({ n: args.n, about: args.about, fromCall: args.from_call, template: args.template, save: args.save === true }));
    const name = needed(args.name, "name");
    if (args.action === "show") return await service.getPersona(ctx, agent, name);
    if (args.action === "on" || args.action === "off") return await service.switchPersona(ctx, agent, name, args.action === "on");
    if (args.action === "rm") return await service.dropPersona(ctx, agent, name);
    const input = service.WritePersonaInput.parse({
      goal: args.goal,
      style: args.style,
      about: args.about,
      facts: args.facts,
      rename: args.rename,
      llm: args.llm,
      tts: args.tts,
      voice: args.voice,
      expects: args.expects,
      tags: args.tags,
      interrupts: args.interrupts,
      pauseS: args.pause_s,
      backchannels: args.backchannels,
      speed: args.speed,
      ambience: args.ambience,
      backgroundNoise: args.background_noise,
    });
    return await service.writePersona(ctx, agent, name, args.action, input);
  },
});

// A run or a simulation outlives the host's patience: past the wait, what it has so far, and a later `wait` picks it up.
async function waited(inFlight: Map<string, InFlight>, agent: string, going: InFlight, waitS: number): Promise<unknown> {
  const late = Symbol("late");
  try {
    const done = await Promise.race([going.pending, new Promise((rung) => setTimeout(() => rung(late), waitS * 1000))]);
    if (done === late) return going.soFar();
    inFlight.delete(agent);
    return done;
  } catch (failed) {
    inFlight.delete(agent);
    throw failed;
  }
}

function transcriptLine(transcript: string[], entry: { type: string; data: Record<string, unknown> }): void {
  if (entry.type === "turn.user") transcript.push(`caller: ${String(entry.data["text"] ?? "")}`);
  if (entry.type === "turn.agent") transcript.push(`agent: ${String(entry.data["text"] ?? "")}`);
  if (entry.type === "tool.call") transcript.push(`tool: ${String(entry.data["name"] ?? "?")}(${JSON.stringify(entry.data["arguments"] ?? {})})`);
}

export type { ToolContext };
