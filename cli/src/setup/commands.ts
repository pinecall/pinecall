/** `pinecall setup`: the runtime on this machine, chosen on a screen — what it can run, each stage, the keys — and run. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError } from "../errors.js";
import { confirm } from "../kit/confirm.js";
import * as render from "./render/index.js";
import * as service from "./service.js";

const SETUP = `
Reads this machine through the runtime (pinecall-runtime setup --recommend: the card and its
memory, Apple silicon, RAM, cores, Docker, an Ollama already running, which vendors' key
variables are set) and shows every model measured for a voice agent — whether it fits beside
the ears, the voice and the embedder, the time to its first token, whether it took a message,
answered from the documents and made small talk — with the stack this machine runs best
already picked. Then one of five ways: the recommended stack, all local, with keys, stage by
stage (the ears, the end of turn, the thinking, the voice, the judge, the caller: each a list to
type into, local/<tag> taking any model Ollama has) or chat only. A key is never typed here:
the screen says where each is (the environment, a shell file not yet sourced, nowhere) and the
runtime reads it or asks. Enter runs \`pinecall-runtime setup --yes\` with the answers and
leaves it running: Postgres, Redis and LiveKit in Docker, the schema, a key this CLI finds by
itself in ~/.pinecall/local.json, the models pulled once, the gateway and a worker.

In a project whose key points at a gateway on another host (the cloud, a server), this machine is
neither scanned nor set up: the host advises, from what it serves and what it lends, a stage at a
time — an open model it serves (no key), a vendor it lends (none of yours), your org's own key,
or one your org must bring — and its operator also sees its machine. A key it needs that this
shell exports is offered to your org on that host (tried there before it is kept, never printed);
the stack is then an agent's, with pinecall agent set.

A flag names a stage and that stage is not asked; --yes asks nothing and runs the recommended
stack as the flags amend it, as a pipe or a script does; --recommend prints the reading and
stops, as JSON under --json.

Examples
  $ pinecall setup
  $ pinecall setup --yes
  $ pinecall setup --llm local/qwen3:30b-a3b-instruct-2507-q4_K_M --judge local/gemma4:12b
  $ pinecall setup --recommend --json
`;

export function register(program: Command, ctx: Context): void {
  program
    .command("setup")
    .description("the runtime on this machine, chosen on a screen and run")
    .option("--stt <choice>", "who hears: local, local/<whisper model>, or a vendor")
    .option("--turn <who>", "who ends the caller's turn: stt, smart-turn or livekit")
    .option("--llm <choice>", "who thinks: local, local/<ollama tag>, or a vendor[/model]")
    .option("--tts <choice>", "who speaks: local, or a vendor")
    .option("--judge <choice>", "who judges a finished call; the thinking's model when left out")
    .option("--caller <choice>", "who plays the simulated caller; the thinking's model when left out")
    .option("--email <address>", "who signs in to the console")
    .option("--chat-only", "written calls alone: no LiveKit, no worker, no ears, no voice")
    .option("-y, --yes", "ask nothing: the recommended stack, as the flags amend it")
    .option("--recommend", "read this machine and print what fits it; set nothing up")
    .addHelpText("after", SETUP)
    .action(async (flags) => {
      const remote = service.anotherHost(ctx.credentials());
      if (remote !== undefined) {
        const advice = await service.remoteAdvice(ctx, remote, service.keysInShellFiles());
        ctx.io.result(advice, render.adviceLines);
        if (flags.recommend === true || !ctx.io.interactive || ctx.io.json) return;
        for (const one of advice.stages) {
          const vendor = one.choice.split("/")[0]!;
          if (one.key?.inEnvironment !== true) continue;
          if (!(await confirm(`give ${one.key.variable} from this shell to your org on ${remote}, for ${one.stage}? [y/N] `, ctx.io))) continue;
          await service.addKeyFromEnvironment(ctx, vendor);
          ctx.io.info(`${vendor}: key tried on ${remote} and kept, sealed there; never printed here`);
        }
        return;
      }
      const read = service.readMachine(ctx.processEnv);
      if (flags.recommend === true) {
        ctx.io.result(read, render.recommendationLines);
        return;
      }
      const named: Partial<service.Answers> = {
        ...(flags.stt === undefined ? {} : { stt: flags.stt }),
        ...(flags.turn === undefined ? {} : { turn: service.turnOf(flags.turn) }),
        ...(flags.llm === undefined ? {} : { llm: flags.llm }),
        ...(flags.tts === undefined ? {} : { tts: flags.tts }),
        ...(flags.judge === undefined ? {} : { judge: flags.judge }),
        ...(flags.caller === undefined ? {} : { caller: flags.caller }),
        ...(flags.email === undefined ? {} : { email: flags.email }),
        ...(flags.chatOnly === true ? { chatOnly: true } : {}),
      };
      const terminal = ctx.io.terminal;
      let answers: service.Answers | undefined = service.answersFrom(read, named);
      if (flags.yes !== true && terminal !== undefined) {
        answers = await render.wizard(
          { read, vendors: service.readVendors(ctx.processEnv), env: ctx.processEnv, keysInFiles: service.keysInShellFiles(), flags: named },
          terminal,
        );
        if (answers === undefined) return;
      }
      for (const line of render.answersLines(answers)) ctx.io.info(line);
      const code = await service.runRuntime(service.flagsOf(answers), ctx.processEnv);
      if (code !== 0) throw new PinecallError(`pinecall-runtime setup ended with exit ${code}`);
    });
}
