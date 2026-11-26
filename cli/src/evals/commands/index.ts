/** `pinecall test | simulate | eval | runs | cases | personas`: the goldens, simulated callers, a call checked again, the runs, the dataset. */

import { existsSync, watch } from "node:fs";

import type { Command } from "@commander-js/extra-typings";

import { listenTo } from "../../calls/service/listening.js";
import { lineFor, metricsLine } from "../../calls/render.js";
import type { Context } from "../../context.js";
import { errorMessage, PinecallError, UsageError } from "../../errors.js";
import { isDirectory } from "../../project/layout.js";
import * as render from "../render/index.js";
import * as service from "../service/index.js";
import { HELP } from "../help.js";

import { registerCases, registerPersonas, registerRuns } from "./dataset.js";
import { numberOf, repeated } from "../../kit/flags.js";
import { A_FOLDER, benchmarkTheRun, GATE_UNDER, namesTheReport, registerBenchmark, REPORT_FLAGS, type ReportFlags } from "./benchmark.js";
import { compareAtTheTerminal, simulateAtTheTerminal, test } from "./terminal.js";

export function register(program: Command, ctx: Context): void {
  program
    .command("test")
    .description("the goldens, run through the agent wherever it is held")
    .argument("[paths...]", "files or directories of goldens; the agent's agents/<name>/test/goldens when none")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .option("--model <m>", "a column of the matrix: vendor/model; say it again for another", repeated)
    .option("--grep <x>", "only the goldens whose name matches")
    .option("--watch", "run again whenever a golden changes")
    .option("--voice", "ring 2: the same goldens said out loud on a real line")
    .option("--background-noise <dB>", "dB under the caller, on a spoken run")
    .option("--ambience <what>", service.AMBIENCES.join(" | "))
    .option("--packet-loss <share>", "the share of the caller's packets lost, 0 to 1")
    .option("--files", "the golden files alone, without the dataset")
    .option("--case <name>", "a case of the org's dataset, by name, whatever its status; again for another", repeated)
    .option("--dataset", "every case a person approved, alone: the nightly")
    .option("--version <n>", "every call on that version of the agent's settings")
    .addHelpText("after", HELP.test)
    .action(async (paths, flags) => {
      const input = service.SuiteInput.parse({
        ...service.whatPlays({ files: flags.files, dataset: flags.dataset, cases: flags.case, paths: paths.length > 0, voice: flags.voice }),
        voice: flags.voice === true,
        backgroundNoise: numberOf("--background-noise", flags.backgroundNoise),
        ambience: flags.ambience,
        packetLoss: numberOf("--packet-loss", flags.packetLoss),
        models: flags.model ?? [],
        cases: flags.case,
        version: numberOf("--version", flags.version),
      });
      await test(ctx, paths, { file: flags.file, agent: flags.agent, grep: flags.grep, watch: flags.watch === true }, input);
    });

  program
    .command("simulate")
    .description("a model plays one persona against the agent, live, and the call is scored at hang-up")
    .requiredOption("--persona <name>", "one of the agent's personas: pinecall personas lists them; again for another caller, compared", repeated)
    .option("--judge", "read back the call.score the log seals on, and print every judge")
    .option("--turns <n>", "how many turns the caller improvises before hanging up", String(service.TURNS))
    .option("--voice", "a real line: a room, and the caller in a person's voice")
    .option("--listen", "the call on this machine's speakers while it happens; turns --voice on")
    .option("--background-noise <dB>")
    .option("--ambience <what>")
    .option("--packet-loss <share>")
    .option("--pause <seconds>", "silence before each of the caller's lines, over the persona's; 0 answers at once")
    .option("--via <webrtc|sip>", "how the caller reaches the agent on a spoken call: in its room, or ringing it by phone over SIP (the sandbox's)")
    .option("--delay <ms>", "the caller's network holds every packet this long, 0 to 2000")
    .option("--jitter <ms>", "how far that hold moves from packet to packet, 0 to 500")
    .option("--rate <kbps>", "the kilobits a second the caller's network carries; a voice needs about 64")
    .option("--goal <text>", "what the caller phones about this run, in the first person, over the persona's goal and the briefing")
    .option("--llm <vendor/model>", "the model that plays the caller this run; the persona's when unsaid")
    .option("--tts <vendor>", "the vendor the caller's voice is read by this run")
    .option("--caller-voice <id>", "the caller's voice this run: pinecall voices list names them")
    .option("--against <values>", "the agent on these for this run: stt=, llm=, tts=, voice=, language=, temperature=, end_of_turn=, or realtime= for a model that hears and speaks; again for another, compared", repeated)
    .option("--repeats <n>", "how many times the caller rings under each configuration, 1 to 10: more than once is a comparison, read as how often each got it done")
    .option("--report [dir]", `the benchmark written when the calls end, into this folder (${A_FOLDER}): turns --judge on`)
    .option(REPORT_FLAGS[0]![0], `with --report: ${REPORT_FLAGS[0]![1]}`)
    .option(REPORT_FLAGS[1]![0], `with --report: ${REPORT_FLAGS[1]![1]}`)
    .option(REPORT_FLAGS[2]![0], `with --report: ${REPORT_FLAGS[2]![1]}`)
    .option(REPORT_FLAGS[3]![0], `with --report: ${REPORT_FLAGS[3]![1]}`)
    .option(REPORT_FLAGS[4]![0], `with --report: ${REPORT_FLAGS[4]![1]}`)
    .option("--condition <name[:line]>", "with --report: the same calls placed again under this line, as television-20:ambience=television,background-noise=20; again for each, the first being the line the others are read against", repeated)
    .option(GATE_UNDER[0], `with --report: ${GATE_UNDER[1]}`, repeated)
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .addHelpText("after", HELP.simulate)
    .action(async (flags) => {
      const listen = flags.listen === true;
      if (listen && flags.voice !== true) ctx.io.info("--listen is a call with audio in it: --voice is on");
      const reported = flags.report !== undefined;
      const reportFlags = flags as ReportFlags;
      if (!reported && namesTheReport(reportFlags)) throw new UsageError("--floor, --ceiling, --baseline, --gate and --gate-under are the report's: add --report");
      const conditions = (flags.condition ?? []).map(service.parseCondition);
      service.requireTold(conditions);
      const namesALine = [flags.backgroundNoise, flags.ambience, flags.packetLoss, flags.via, flags.delay, flags.jitter, flags.rate].some((said) => said !== undefined);
      if (conditions.length > 0 && namesALine) throw new UsageError("with --condition the line is each condition's: say it there, as television-20:ambience=television,background-noise=20");
      if (conditions.length > 1 && !reported) throw new UsageError("several conditions are read in one report: add --report");
      if (conditions.some((condition) => Object.keys(condition.line ?? {}).length > 0) && flags.voice !== true && !listen) throw new UsageError("a condition changes the line of a spoken call: add --voice");
      if (reported && flags.judge !== true) ctx.io.info("--report is the calls as their judges read them: --judge is on");
      const typed = service.SimulateInput.parse({
        persona: flags.persona[0],
        morePersonas: flags.persona.slice(1),
        judge: flags.judge === true || reported,
        voice: flags.voice === true || listen,
        turns: numberOf("--turns", flags.turns),
        backgroundNoise: numberOf("--background-noise", flags.backgroundNoise),
        ambience: flags.ambience,
        packetLoss: numberOf("--packet-loss", flags.packetLoss),
        pauseS: numberOf("--pause", flags.pause),
        via: flags.via,
        delayMs: numberOf("--delay", flags.delay),
        jitterMs: numberOf("--jitter", flags.jitter),
        rateKbps: numberOf("--rate", flags.rate),
        goal: flags.goal,
        llm: flags.llm,
        tts: flags.tts,
        callerVoice: flags.callerVoice,
        repeats: numberOf("--repeats", flags.repeats),
      });
      // One condition has nothing to be read against: its line is the run's, as the line's own flags would say it.
      const input = conditions.length === 1 ? service.inputUnder(typed, conditions[0]!) : typed;
      // The gateway places the call and keeps the personas: an agent with no folder (one built in Studio) is its slug.
      const agent = ctx.slug("simulate", { file: flags.file, agent: flags.agent });
      const against = (flags.against ?? []).map(service.parseAgainst);
      if (reported) {
        if (listen) throw new UsageError("--listen plays one call: a report is of calls placed together");
        if (input.goal !== undefined && input.morePersonas.length > 0) throw new UsageError("--goal is what one caller phones about: with several callers, each phones about its own");
        await benchmarkTheRun(ctx, agent, input, against.length === 0 ? [{}] : against, flags.report === true || flags.report === undefined ? A_FOLDER : flags.report, reportFlags, conditions);
        return;
      }
      // Several configurations, several callers, or one rung several times, are several calls: placed together, read as one table.
      if (against.length > 1 || input.repeats > 1 || input.morePersonas.length > 0) {
        if (listen) throw new UsageError("--listen plays one call: a comparison runs several at once");
        if (input.goal !== undefined && input.morePersonas.length > 0) throw new UsageError("--goal is what one caller phones about: with several callers, each phones about its own");
        await compareAtTheTerminal(ctx, agent, input, against.length === 0 ? [{}] : against);
        return;
      }
      service.requireHeld(await simulateAtTheTerminal(ctx, agent, input, listen, against[0]));
    });

  registerBenchmark(program, ctx);

  program
    .command("eval")
    .description("ring 3: one real call, re-evaluated by the runtime's code checks")
    .argument("<call-id>")
    .option("--policy <file>", "{\"banned\": […], \"budget\": {…}}")
    .addHelpText("after", HELP.eval)
    .action(async (call, flags) => {
      const answer = await service.replayCall(ctx, call, service.readPolicy(flags.policy));
      ctx.io.result(answer, render.replayed);
      if (!answer.passed) throw new PinecallError("a check is broken");
    });

  registerRuns(program, ctx);
  registerCases(program, ctx);
  registerPersonas(program, ctx);
}

