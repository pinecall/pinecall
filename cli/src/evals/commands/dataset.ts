/** `pinecall runs | cases | personas`: the runs the gateway kept, the org's dataset, the agent's simulated callers. */

import { Option, type Command } from "@commander-js/extra-typings";

import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import { HELP } from "../help.js";
import * as render from "../render/index.js";
import * as service from "../service/index.js";
import { numberOf, repeated } from "../../kit/flags.js";
import { simulateAtTheTerminal } from "./terminal.js";

export function registerRuns(program: Command, ctx: Context): void {
  const runs = program.command("runs").description("the runs this gateway has done: list, show, diff, promote a call, watch the drift").addHelpText("after", HELP.runs);
  runs
    .command("list", { isDefault: true })
    .description("the newest runs, with how each ended")
    .option("--limit <n>", `how many, newest first, 1 to ${service.RUNS_MOST}`, "20")
    .action(async (flags) => ctx.io.result(await service.listRuns(ctx, service.RunsLimit.parse(numberOf("--limit", flags.limit) ?? 20)), render.runs));
  runs
    .command("show")
    .description("one run whole: its matrix, each golden's verdicts and latencies")
    .argument("<id>")
    .action(async (id) => {
      const shown = await service.showRun(ctx, id);
      ctx.io.result(shown, (one) => render.matrix(one.run, one.latencies, service.DECLARED_AS));
      if ((shown.run.matrix?.failures.length ?? 0) > 0) throw new PinecallError("a golden broke in that run");
    });
  runs
    .command("diff")
    .description("which goldens moved between two runs")
    .argument("<before>")
    .argument("<after>")
    .action(async (before, after) => {
      const diffed = await service.diffRuns(ctx, before, after);
      ctx.io.result(diffed, render.moved);
      if (diffed.moved.some((one) => one.now === "broken")) throw new PinecallError("a golden broke between the two");
    });
  runs
    .command("promote")
    .description("the golden a real call makes, written as a candidate")
    .argument("<call-id>")
    .option("--name <x>")
    .option("--agent <name>", "whose candidates; the project's only agent when left out")
    .option("--out <dir>", "the agent's test/candidates when left out")
    .option("--from-seq <n>", "cut the call there: the state as it stood, every caller turn after it")
    .action(async (call, flags) => {
      const out = flags.out ?? ctx.agent("runs promote", { agent: flags.agent }).candidates;
      const input = service.PromoteInput.parse({ call, name: flags.name, out, fromSeq: numberOf("--from-seq", flags.fromSeq) });
      ctx.io.result(await service.promoteCall(ctx, input), (done) => render.promoted(done, input.fromSeq));
    });
  runs
    .command("drift")
    .description("each judge's held-rate over two windows of finished calls")
    .option("--agent <slug>", "the agent, from any folder; the one beside you when left out")
    .option("--window <span>", "90m, 24h, 7d", "7d")
    .option("--baseline <span>", "the time before the window", "30d")
    .option("--threshold <points>", "the drop that fails", String(service.THRESHOLD))
    .option("--limit <n>", `the newest calls read, at most ${service.DRIFT_CALLS}`)
    .action(async (flags) => {
      const window = service.secondsOf(flags.window);
      const baseline = service.secondsOf(flags.baseline);
      if (window === null || baseline === null) throw new UsageError("a window is a number and one of s, m, h, d — 90m, 24h, 7d");
      const found = await service.driftOf(ctx, service.DriftInput.parse({ agent: ctx.slug("runs drift", { agent: flags.agent }), window, baseline, threshold: numberOf("--threshold", flags.threshold), limit: numberOf("--limit", flags.limit) }));
      ctx.io.result(found, render.drift);
      if (service.drifted(found)) throw new PinecallError("a judge fell further than the threshold allows");
    });
}

export function registerCases(program: Command, ctx: Context): void {
  const cases = program.command("cases").description("the org's dataset: real calls kept as cases — read, approve, dismiss, pull into the repository; a golden written by hand added").addHelpText("after", HELP.cases);
  // The cases live on the gateway: --agent is a slug, from any folder. Only `pull` writes into the project; `add` reads from it.
  const agentOf = (flags: { agent?: string | undefined }): service.EvalCase["agent"] => ctx.slug("cases", { agent: flags.agent });
  cases
    .command("list", { isDefault: true })
    .description("the agent's cases, the pending first; --status keeps one")
    .option("--status <status>", service.STATUSES.join(" | "))
    .option("--agent <name>")
    .action(async (flags) => {
      if (flags.status !== undefined && !(service.STATUSES as readonly string[]).includes(flags.status)) throw new UsageError(`--status ${flags.status}: ${service.STATUSES.join(", ")}`);
      const status = flags.status as service.CaseStatus | undefined;
      ctx.io.result(await service.listCases(ctx, agentOf(flags), status), (list) => render.cases(list, status));
    });
  cases.command("groups")
    .description("the agent's case groups: the calls one judge broke on, together").option("--agent <name>").action(async (flags) => {
    const agent = agentOf(flags);
    ctx.io.result(await service.listGroups(ctx, agent), (found) => render.groups(agent, found));
  });
  cases
    .command("show")
    .description("one case whole, or one group with its cases")
    .argument("<name|group>")
    .option("--agent <name>")
    .action(async (named, flags) => {
      if (service.isGroup(named)) ctx.io.result(await service.getGroup(ctx, named), render.group);
      else ctx.io.result(await service.getCase(ctx, agentOf(flags), named), render.oneCase);
    });
  cases.command("propose")
    .description("the judge model's diagnosis of a group: the cause and the smallest fix").argument("<group>").action(async (id) => ctx.io.result(await service.proposeFix(ctx, id), render.proposed));
  cases.command("apply")
    .description("the group's proposed setting, written as a new version of yours").argument("<group>").action(async (id) => ctx.io.result(await service.applyFix(ctx, id), () => render.APPLIED));
  cases.command("persona")
    .description("a caller like the group's, kept as the agent's own persona").argument("<group>").action(async (id) => ctx.io.result(await service.personaOfGroup(ctx, id), (written) => written.personas.map((one) => `${one.name} kept · ${one.goal}`)));
  cases
    .command("approve")
    .description("a case or a whole group approved: the nightly plays it from now on")
    .argument("<name|group>")
    .option("--agent <name>")
    .action(async (named, flags) => {
      if (service.isGroup(named)) ctx.io.result(await service.decideGroup(ctx, named, true), render.groupLines);
      else ctx.io.result(await service.approveCase(ctx, agentOf(flags), named), (one) => render.caseDecided(one));
    });
  cases
    .command("dismiss")
    .description("a case or a whole group dismissed: the agent was right, or the judge was wrong")
    .argument("<name|group>")
    .option("--judge-was-wrong <judge>", "the judge that broke and should have held")
    .option("--note <why>")
    .option("--agent <name>")
    .action(async (named, flags) => {
      if (service.isGroup(named)) {
        ctx.io.result(await service.decideGroup(ctx, named, false, { judgeWasWrong: flags.judgeWasWrong !== undefined, note: flags.note }), render.groupLines);
        return;
      }
      const input = service.DismissInput.parse({ judgeWasWrong: flags.judgeWasWrong, note: flags.note });
      ctx.io.result(await service.dismissCase(ctx, agentOf(flags), named, input), (one) => render.caseDecided(one, input.judgeWasWrong));
    });
  cases.command("reopen")
    .description("a decided case pending again").argument("<name>").option("--agent <name>").action(async (name, flags) => ctx.io.result(await service.reopenCase(ctx, agentOf(flags), name), (one) => render.caseDecided(one)));
  cases.command("forget")
    .description("a case gone; the call it came from stays").argument("<name>").option("--agent <name>").action(async (name, flags) => ctx.io.result(await service.forgetCase(ctx, agentOf(flags), name), render.caseForgotten));
  cases
    .command("pull")
    .description("the case's golden as a file in the agent's goldens, to keep in the repository")
    .argument("<name>")
    .option("--out <dir>", "the agent's goldens folder when left out")
    .option("--agent <name>")
    .action(async (name, flags) => {
      const home = ctx.agent("cases", { agent: flags.agent });
      ctx.io.result(await service.pullCase(ctx, home.name, name, flags.out ?? home.goldens), render.casePulled);
    });
  cases
    .command("add")
    .description("a golden written by hand kept as an approved case, under its name")
    .argument("<file...>", "JSON files, one golden or a list of them each; never a folder")
    .option("--name <name>", "the case's name, for one file whose golden has none; its basename when left out")
    .option("--held-out", "played only when a run names it")
    .option("--agent <name>")
    .action(async (files, flags) => ctx.io.result(await service.addCases(ctx, agentOf(flags), service.AddCasesInput.parse({ files, name: flags.name, heldOut: flags.heldOut === true })), render.casesAdded));
  cases
    .command("keep")
    .description("a finished call kept as an approved case, by name")
    .argument("<call-id>")
    .requiredOption("--name <x>")
    .option("--held-out", "played only when a run names it")
    .action(async (call, flags) => ctx.io.result(await service.keepCall(ctx, service.KeepInput.parse({ call, name: flags.name, heldOut: flags.heldOut === true })), render.caseKept));
}

export function registerPersonas(program: Command, ctx: Context): void {
  const personas = program.command("personas").description("an agent's synthetic callers: Pinecall's switched on or off, its own written, generated, tried").addHelpText("after", HELP.personas);
  const agentOf = (flags: { agent?: string | undefined; file?: string | undefined }): string => ctx.agent("personas", { agent: flags.agent, file: flags.file }).name;
  personas
    .command("list", { isDefault: true })
    .description("the agent's callers: Pinecall's, on or off, and its own")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (flags) => {
      const agent = agentOf(flags);
      const found = await service.listPersonas(ctx, agent);
      const unsent = await service.personasNotPushed(ctx, flags, found);
      ctx.io.result({ personas: found, not_pushed: unsent.names, not_personas: unsent.refused }, () => render.personas(agent, found, unsent.names, unsent.refused));
    });
  personas
    .command("show")
    .description("one caller whole: goal, style, facts, what they expect, how they act")
    .argument("<name>")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (name, flags) => ctx.io.result(await service.getPersona(ctx, agentOf(flags), name), render.persona));
  for (const verb of ["add", "edit"] as const) {
    personas
      .command(verb)
      .description(verb === "add" ? "write one: --goal and --style are needed" : "change what is named and leave the rest")
      .argument("<name>")
      .option("--agent <name>")
      .option("--file <agent.tsx>")
      .option("--goal <goal>", "what they want")
      .option("--style <style>", "how they talk")
      .option("--about <about>", "who they are, in a line")
      .option("--fact <what=said>", "what they know and say when asked; again for another", repeated)
      .option("--expect <line>", "what the agent should do; again for another", repeated)
      .option("--tag <tag>", "again for another", repeated)
      .option("--llm <model>", "the model that plays them")
      .option("--tts <vendor>")
      .option("--voice <voice>")
      .option("--interrupts <0-1>", "on a spoken call, the share of the agent's answers they talk over")
      .option("--pause <s>", "seconds of silence before each line")
      .option("--backchannels <0-1>")
      .option("--speed <0.5-2>")
      .option("--ambience <what>", service.AMBIENCES.join(" | "))
      .option("--background-noise <dB>", "dB under them it plays at; empty for a quiet room")
      .addOption(new Option("--rename <name>", "move it to another name").hideHelp(verb === "add"))
      .action(async (name, flags) => {
        const input = service.WritePersonaInput.parse({
          goal: flags.goal,
          style: flags.style,
          about: flags.about,
          facts: flags.fact === undefined ? undefined : service.factsOf(flags.fact),
          rename: flags.rename,
          llm: flags.llm,
          tts: flags.tts,
          voice: flags.voice,
          expects: flags.expect,
          tags: flags.tag,
          interrupts: numberOf("--interrupts", flags.interrupts),
          pauseS: numberOf("--pause", flags.pause),
          backchannels: numberOf("--backchannels", flags.backchannels),
          speed: numberOf("--speed", flags.speed),
          ambience: flags.ambience,
          backgroundNoise: flags.backgroundNoise === "" ? null : numberOf("--background-noise", flags.backgroundNoise),
        });
        if (verb === "add" && input.rename !== undefined) throw new UsageError("--rename is edit's: add writes the name typed");
        ctx.io.result(await service.writePersona(ctx, agentOf(flags), name, verb, input), (done) => render.personaWritten(verb, done));
      });
  }
  personas
    .command("rm")
    .description("the caller dropped; one of Pinecall's is switched off instead")
    .argument("<name>")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (name, flags) => ctx.io.result(await service.dropPersona(ctx, agentOf(flags), name), render.personaDropped));
  for (const verb of ["on", "off"] as const) {
    personas
      .command(verb)
      .description(`one of Pinecall's switched ${verb} for the agent`)
      .argument("<name>")
      .option("--agent <name>")
      .option("--file <agent.tsx>")
      .action(async (name, flags) => {
        const agent = agentOf(flags);
        ctx.io.result(await service.switchPersona(ctx, agent, name, verb === "on"), (done) => render.personaSwitched(done, agent));
      });
  }
  personas
    .command("try")
    .description("one call against the agent: simulate, without the judge")
    .argument("<name>")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (name, flags) => {
      if (ctx.io.json) throw new UsageError("try prints a call as it happens, not an answer the gateway gave: drop --json");
      await simulateAtTheTerminal(ctx, agentOf(flags), service.SimulateInput.parse({ persona: name }), false);
    });
  personas
    .command("generate")
    .description("callers written by the judge model from the agent; printed, and kept with --save")
    .argument("[n]", "how many callers, 1 to 10", "3")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .option("--about <theme>")
    .option("--from-call <call>", "callers like this call's caller")
    .option("--template <name>", "callers like one of Pinecall's")
    .option("--save", "keep every one as the agent's own")
    .action(async (n, flags) => {
      const input = service.GenerateInput.parse({ n: numberOf("generate", n), about: flags.about, fromCall: flags.fromCall, template: flags.template, save: flags.save === true });
      ctx.io.result(await service.generatePersonas(ctx, agentOf(flags), input), render.generated);
    });
  personas
    .command("push")
    .description("the personas still in files, sent to the gateway once")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .option("--from <folder>", "agents/<agent>/test/personas when left out")
    .action(async (flags) => {
      const home = ctx.agent("personas", { agent: flags.agent, file: flags.file });
      const folder = flags.from ?? home.personas;
      ctx.io.result(await service.pushPersonaFiles(ctx, home.name, folder), (done) => render.pushedFiles(done, folder));
    });
}
