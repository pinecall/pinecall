/** `pinecall start | console | prompt`: the agents served and the console answered, the console opened, the prompt a state produces. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError } from "../errors.js";
import { openInBrowser } from "../kit/browser.js";
import { stateOfCase } from "../calls/service/chat.js";
import { runOnce, serveStart } from "./child.js";
import * as render from "./render.js";
import { consoleLink, start, StartInput } from "./start.js";

const START = `
With nothing after it: the agent served by its language's serve entry, a process this one starts and
watches, one line per log entry on stdout, no port bound and no page served. Beside it this process
holds a socket of its own that answers the console's screens and takes no call. Without --prod it
registers in the sandbox and answers the sandbox's console; with --prod, in production and its console.

At the root of a project of several agents — agents/<name>/agent.tsx — every agent at once, in one
process, each line prefixed by its slug; --agent <name> runs one of them.

Ctrl-C or SIGTERM: the agent's process drains its calls to the next holder and leaves; a second
signal kills it. --inspect is Node's own flag, given to a TypeScript agent's process.

Examples
  $ pinecall start
  clinica-norte · clinica · sandbox · connected to https://cloud.pinecall.io · key from .env · tools 4
  talk to it  https://cloud.pinecall.io/sandbox/a/clinica-norte/playground?login=lc_9f2   (opens within five minutes, once)
`;

const CONSOLE = `
Opens the console of the env this verb acts in, signed in. The key itself never travels: the
gateway mints a one-use code for it, good for five minutes, and the page spends the code for a
key of that browser's own. Without --prod it is the SANDBOX's console; with --prod, production's.
With no agent it opens the org's floor; name one and it opens that agent's screens.
`;

const PROMPT = `
The three regions of the prompt as the model would receive them — the static prefix, the history,
the dynamic blocks at the end — and under them the stage and the tools that stage shows. No
gateway, no key, no call: the agent's own serve entry loads the class and puts it in the state the
file describes.

Examples
  $ pinecall prompt --state agents/clinica-norte/test/goldens/identifica-al-paciente.json
`;

export function register(program: Command, ctx: Context): void {
  program
    .command("start")
    .description("the agents served and the console answered: the process you deploy")
    .argument("[agent.tsx]")
    .option("--agent <name>")
    .option("--show-prompt", "the prompt a fresh instance would produce, then exit; no key, no gateway")
    .option("--events", "the agent's process's lines as it prints them, one JSON entry each, for a pipe")
    .option("--ui", "the full-screen terminal view; keys: p pause · c clear · e events · q quit")
    .option("--inspect [host:port]", "Node's own flag, given to a TypeScript agent's process")
    .option("--inspect-brk [host:port]", "Node's own flag, given to a TypeScript agent's process")
    .addHelpText("after", START)
    .action(async (file, flags) => {
      // Node's own flags pass to the agent's process as they were typed.
      const inspect = [
        ...(flags.inspect === undefined ? [] : [flags.inspect === true ? "--inspect" : `--inspect=${flags.inspect}`]),
        ...(flags.inspectBrk === undefined ? [] : [flags.inspectBrk === true ? "--inspect-brk" : `--inspect-brk=${flags.inspectBrk}`]),
      ];
      const code = await start(ctx, StartInput.parse({ file, agent: flags.agent, showPrompt: flags.showPrompt === true, events: flags.events === true, ui: flags.ui === true, inspect }));
      if (code !== 0) throw new PinecallError(`the agent's process left with ${code}`);
    });

  program
    .command("console")
    .description("the console in a browser, signed in: the sandbox's, or production's with --prod")
    .argument("[agent]")
    .option("--no-open", "print the URL and do not open a browser")
    .addHelpText("after", CONSOLE)
    .action(async (agent, flags) => {
      const url = await consoleLink(ctx, agent);
      ctx.io.result({ url }, (one) => render.consoleLine(one.url));
      if (flags.open) openInBrowser(url);
    });

  program
    .command("prompt")
    .description("the exact prompt a state would produce, offline")
    .argument("[agent.tsx]")
    .option("--agent <name>")
    .option("--state <file>", "a goldens file: the state of one of its cases")
    .option("--case <n>", "which case of that file", "0")
    .option("--channel <channel>", "phone | web | whatsapp", "phone")
    .option("--medium <how>", "voice | text; the channel's when left out")
    .addHelpText("after", PROMPT)
    .action(async (file, flags) => {
      const home = ctx.agent("prompt", { file, agent: flags.agent });
      // No file is the state the class opens a call in.
      const state = flags.state === undefined ? {} : stateOfCase(flags.state, Number(flags.case));
      const pairs = Object.entries(state).flatMap(([field, value]) => ["--state", `${field}=${JSON.stringify(value)}`]);
      const medium = flags.medium === undefined ? [] : ["--medium", flags.medium];
      const args = ["--file", home.file, "--slug", home.name, ...pairs, "--channel", flags.channel, ...medium, "--show-machine"];
      const code = await runOnce(serveStart(undefined, home.file, "prompt", args, { root: home.root }, ctx.processEnv), ctx.io.stdout, ctx.io.stderr);
      if (code !== 0) throw new PinecallError(`the serve entry left with ${code}`);
    });
}
