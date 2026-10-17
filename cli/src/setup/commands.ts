/** `pinecall setup`: the runtime on this machine, chosen on a screen — what it can run, each stage, the keys — and run. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError } from "../errors.js";
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

It is this machine's runtime only: in a project whose key points at a gateway on another host
(the cloud, a server), nothing here is scanned or set up, and it says so; that host's models are
set there, with pinecall-runtime setup, or in the console.

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
      const credentials = ctx.credentials();
      const remote = service.anotherHost(credentials);
      if (remote !== undefined) throw new PinecallError(service.ANOTHER_HOST(remote, credentials.source));
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
