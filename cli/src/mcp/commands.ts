/** `pinecall mcp`: the MCP server an assistant runs this CLI as, and `install`, which adds it to every assistant here. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError, UsageError } from "../errors.js";
import { version } from "../version.js";
import { installEverywhere, listHosts, renderDone, renderListed } from "./install/installing.js";

const MCP = `
With nothing after it, the MCP server on stdin and stdout, for an assistant to launch: the tools
sign this machine in, link a project, hold the agent, chat with it, test it. It starts no process
of its own. Every tool acts in the sandbox, and in production when asked with prod: true; your
org's switch still decides.

install writes \`npx -y pinecall@latest mcp\` into every assistant installed here — Claude Code,
Claude Desktop, Codex, Cursor, Windsurf, Antigravity, Gemini CLI — replacing an older entry,
copying each file to .bak first, and leaving every other setting and comment as it was. No key
is written: the server reads the project's .env.

Examples
  $ pinecall mcp install --list
`;

const BOTH_ENVS = "pinecall mcp acts in both envs: a tool asks for production with prod: true";

export function register(program: Command, ctx: Context): void {
  const mcp = program.command("mcp").description("the MCP server an assistant runs this CLI as, and `install`, which adds it to every assistant here").addHelpText("after", MCP);
  mcp
    .command("serve", { isDefault: true, hidden: true })
    .action(async () => {
      if (ctx.env === "production") throw new UsageError(BOTH_ENVS);
      // The SDK is loaded only here: `pinecall prompt` must not pay for it.
      const { serve } = await import("./server.js");
      await serve(version(), ctx.processEnv, ctx.io);
    });
  mcp
    .command("install")
    .description("Pinecall written into every assistant on this machine")
    .option("--list", "every assistant, and whether Pinecall is in it; changes nothing")
    .option("--remove", "take Pinecall out of every assistant")
    .action((flags) => {
      if (flags.list === true) {
        ctx.io.result(listHosts(), renderListed);
        return;
      }
      const done = installEverywhere(flags.remove === true);
      ctx.io.result(done, (all) => renderDone(all, flags.remove === true));
      if (done.some((one) => one.did === "failed")) throw new PinecallError("an assistant's config could not be written");
    });
}
