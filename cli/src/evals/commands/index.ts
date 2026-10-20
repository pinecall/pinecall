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
import { simulateAtTheTerminal, test } from "./terminal.js";

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
    .option("--case <name>", "a case of the org's dataset, by name, whatever its status; again for another", repeated)
    .option("--dataset", "every case a person approved: the nightly")
    .option("--version <n>", "every call on that version of the agent's settings")
    .addHelpText("after", HELP.test)
    .action(async (paths, flags) => {
      const input = service.SuiteInput.parse({
        voice: flags.voice === true,
        backgroundNoise: numberOf("--background-noise", flags.backgroundNoise),
        ambience: flags.ambience,
        packetLoss: numberOf("--packet-loss", flags.packetLoss),
        models: flags.model ?? [],
        cases: flags.case,
        dataset: flags.dataset === true,
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
    .option("--llm <vendor/model>", "the model that plays the caller this run; the persona's when unsaid")
    .option("--tts <vendor>", "the vendor the caller's voice is read by this run")
    .option("--caller-voice <id>", "the caller's voice this run: pinecall voices list names them")
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
        llm: flags.llm,
        tts: flags.tts,
        callerVoice: flags.callerVoice,
      });
      const agent = ctx.agent("simulate", { file: flags.file, agent: flags.agent }).name;
      const said = await simulateAtTheTerminal(ctx, agent, input, listen);
      if (service.exitCodeOf(said) !== 0) throw new PinecallError("a judge answered broken");
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

