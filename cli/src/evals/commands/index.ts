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
    .requiredOption("--persona <name>", "one of the agent's personas: pinecall personas lists them")
    .option("--judge", "read back the call.score the log seals on, and print every judge")
    .option("--turns <n>", "how many turns the caller improvises before hanging up", String(service.TURNS))
    .option("--voice", "a real line: a room, and the caller in a person's voice")
    .option("--listen", "the call on this machine's speakers while it happens; turns --voice on")
    .option("--background-noise <dB>")
    .option("--ambience <what>")
    .option("--packet-loss <share>")
    .option("--pause <seconds>", "silence before each of the caller's lines, over the persona's; 0 answers at once")
    .option("--goal <text>", "what the caller phones about this run, in the first person, over the persona's goal and the briefing")
    .option("--llm <vendor/model>", "the model that plays the caller this run; the persona's when unsaid")
    .option("--tts <vendor>", "the vendor the caller's voice is read by this run")
    .option("--caller-voice <id>", "the caller's voice this run: pinecall voices list names them")
    .option("--against <values>", "the agent on these for this run: stt=, llm=, tts=, voice=, language=, temperature=, end_of_turn=; again for another, compared", repeated)
    .option("--repeats <n>", "how many times the caller rings under each configuration, 1 to 10: more than once is a comparison, read as how often each got it done")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .addHelpText("after", HELP.simulate)
    .action(async (flags) => {
      const listen = flags.listen === true;
      if (listen && flags.voice !== true) ctx.io.info("--listen is a call with audio in it: --voice is on");
      const input = service.SimulateInput.parse({
        persona: flags.persona,
        judge: flags.judge === true,
        voice: flags.voice === true || listen,
        turns: numberOf("--turns", flags.turns),
        backgroundNoise: numberOf("--background-noise", flags.backgroundNoise),
        ambience: flags.ambience,
        packetLoss: numberOf("--packet-loss", flags.packetLoss),
        pauseS: numberOf("--pause", flags.pause),
        goal: flags.goal,
        llm: flags.llm,
        tts: flags.tts,
        callerVoice: flags.callerVoice,
        repeats: numberOf("--repeats", flags.repeats),
      });
      const agent = ctx.agent("simulate", { file: flags.file, agent: flags.agent }).name;
      const against = (flags.against ?? []).map(service.parseAgainst);
      // Several configurations, or one rung several times, are several calls: placed together, read as one table.
      if (against.length > 1 || input.repeats > 1) {
        if (listen) throw new UsageError("--listen plays one call: a comparison runs several at once");
        await compareAtTheTerminal(ctx, agent, input, against.length === 0 ? [{}] : against);
        return;
      }
      service.requireHeld(await simulateAtTheTerminal(ctx, agent, input, listen, against[0]));
    });

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

