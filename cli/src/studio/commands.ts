/** `pinecall studio`: the agents built in the console's Studio — listed, made, pulled to a file and pushed back, a tool tried, deployed, their code. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { numberOf } from "../kit/flags.js";
import * as render from "./render.js";
import * as service from "./service.js";

const STUDIO = `
A Studio agent is written in the console, not as a class: its instructions, how it opens a call,
the HTTP requests it may make and the data it collects, kept as one definition. Every save is a
release. Pinecall holds the agent itself, so \`pinecall chat <name>\` talks to it with nothing
started; \`pinecall deploy list\` shows it beside the org's hosted apps, and \`deploy stop\`,
\`start\`, \`rm\` and \`rollback\` work on it by name.

pull writes the definition to a file with the release it was read at; push saves the file as the
next release over that one and writes the new number into it, and is refused when someone saved
meanwhile: pull again. A header's value names a secret as {{secrets.NAME}} — set it with
\`pinecall secrets set\`, never in the file. The sandbox's unless --prod; deploy is asked from the
sandbox and lands in production.

Examples
  $ pinecall studio new front-desk
  front-desk: made in the sandbox as release 1 — \`pinecall studio pull front-desk\` writes it to a file
  $ pinecall studio pull front-desk
  front-desk: release 1 written to front-desk.studio.json
  $ pinecall studio push front-desk --note "books the visit"
  front-desk: front-desk.studio.json saved as release 2 in the sandbox
  $ pinecall studio try front-desk find_slot day=2026-10-21 people=2
  200 · 184 ms
  {
    "free": 2
  }
  $ pinecall studio deploy front-desk --note "first week"
  front-desk: in production as release 1, answering from its next call
`;

export function register(program: Command, ctx: Context): void {
  const studio = program
    .command("studio")
    .description("agents built in the console's Studio: made, pulled to a file and pushed back, a tool tried, deployed, their code")
    .addHelpText("after", STUDIO);
  studio
    .command("list", { isDefault: true })
    .description("the org's Studio agents here: each one's release, who saved it, whether it is stopped")
    .action(async () => ctx.io.result(await service.listAgents(ctx), render.agents));
  studio
    .command("new")
    .description("make one, starting from the template the gateway gives")
    .argument("<name>")
    .option("--note <why>", "kept with the release", "")
    .action(async (name, flags) => ctx.io.result(await service.createAgent(ctx, name, flags.note), render.made));
  studio
    .command("pull")
    .description("write its definition to a file, with the release it was read at")
    .argument("<name>")
    .option("--out <file>", "<name>.studio.json unless given")
    .action(async (name, flags) => ctx.io.result(await service.pullAgent(ctx, name, flags.out), render.pulled));
  studio
    .command("push")
    .description("save the file as the next release, over the release it was pulled at")
    .argument("<name>")
    .option("--file <file>", "<name>.studio.json unless given")
    .option("--note <why>", "kept with the release", "")
    .action(async (name, flags) => ctx.io.result(await service.pushAgent(ctx, name, flags.file, flags.note), render.pushed));
  studio
    .command("try")
    .description("send one tool's request once, as a call would, and print its status, time and body")
    .argument("<name>")
    .argument("<tool>")
    .argument("[arguments...]", "key=value each; a number or true/false is read as one")
    .action(async (name, tool, words) => ctx.io.result(await service.tryTool(ctx, name, tool, service.toolArguments(words)), render.tried));
  studio
    .command("deploy")
    .description("the sandbox's release into production: its newest unless --release")
    .argument("<name>")
    .option("--release <n>", "the sandbox's release to deploy")
    .option("--note <why>", "kept with production's release", "")
    .action(async (name, flags) => ctx.io.result(await service.deployAgent(ctx, name, numberOf("--release", flags.release), flags.note), render.deployed));
  studio
    .command("code")
    .description("the agent as a TypeScript project: saved as <name>.zip, or written into --out")
    .argument("<name>")
    .option("--out <dir>", "a folder to write the project's files into instead of the zip")
    .action(async (name, flags) => ctx.io.result(await service.downloadCode(ctx, name, flags.out), render.code));
}
