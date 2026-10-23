/** `pinecall deploy`: this project run on Pinecall — uploaded as a release, installed and started there. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError } from "../errors.js";
import * as render from "./render.js";
import * as service from "./service.js";

const DEPLOY = `
Pinecall runs the project the way \`pinecall start\` would, in a container of its own: it installs
the dependencies from the lockfile, starts the agents on a token it minted for the app, and hands
them the org's secrets (\`pinecall secrets\`) as environment variables. The release it replaces keeps
answering until the new one's agents register, so a deploy cuts no call; one that does not install,
exits, or registers nothing is reported with its last lines, and the one before keeps serving.

What travels is every file the project's .gitignore files leave in — read where each sits, no git
asked — never node_modules, .venv, .git, dist or any .env. The sandbox's unless --prod.

Examples
  ~/acme-support $ pinecall deploy --prod --note "reads the order's eta back"
  acme-support: release 4 sent · 38 KB · 3b507661b052
  acme-support: Pinecall installs and starts it; the release before keeps answering meanwhile
  acme-support: release 4 is live
`;

export function register(program: Command, ctx: Context): void {
  const deploy = program.command("deploy").description("run this project on Pinecall: uploaded as a release, installed and started there").addHelpText("after", DEPLOY);
  deploy
    .command("up", { isDefault: true })
    .description("upload this folder as the app's next release, and follow it until it is live")
    .option("--name <app>", "this folder's name unless given")
    .option("--note <why>", "kept with the release", "")
    .option("--no-follow", "upload and return, without waiting for it to go live")
    .action(async (flags) => {
      const name = service.appName(ctx, flags.name);
      const sent = await service.uploadRelease(ctx, name, flags.note);
      ctx.io.result(sent, render.sent);
      if (flags.follow) await follow(ctx, sent);
    });
  deploy
    .command("list")
    .description("the org's hosted apps: the newest release, the one serving, and why one failed")
    .action(async () => ctx.io.result(await service.listApps(ctx), render.apps));
  deploy
    .command("releases")
    .description("one app's releases, newest first")
    .option("--name <app>")
    .action(async (flags) => ctx.io.result(await service.listReleases(ctx, service.appName(ctx, flags.name)), render.releases));
  deploy
    .command("rollback")
    .description("release n's sources kept again as the next release, and followed")
    .argument("<release>")
    .option("--name <app>")
    .option("--no-follow")
    .action(async (release, flags) => {
      const sent = await service.rollbackRelease(ctx, service.appName(ctx, flags.name), Number(release));
      ctx.io.result(sent, (one) => render.rolledBack(one, Number(release)));
      if (flags.follow) await follow(ctx, sent);
    });
  deploy
    .command("logs")
    .description("the last lines of the app's process, fresh from Pinecall")
    .option("--name <app>")
    .option("--follow", "keep printing the lines that come, until Ctrl-C")
    .action(async (flags) => {
      const name = service.appName(ctx, flags.name);
      if (flags.follow !== true) {
        const found = await service.readLogs(ctx, name, service.LOGS_WITHIN_MS);
        ctx.io.result(found, render.logs);
        if (found.none) throw new PinecallError("no lines yet");
        return;
      }
      // A follow prints the first read as it settles, then every line that comes, until Ctrl-C.
      const print = (lines: readonly string[]): void => lines.forEach((line) => ctx.io.print(line));
      await service.readLogs(ctx, name, service.LOGS_WITHIN_MS, { onFirst: (first) => print(render.logs(first)), onMore: print }, ctx.signal);
    });
  deploy
    .command("stop")
    .description("the process drains and nothing runs; its releases and token stay")
    .option("--name <app>")
    .action(async (flags) => ctx.io.result(await service.stopApp(ctx, service.appName(ctx, flags.name)), render.stopped));
  deploy
    .command("start")
    .description("a stopped app runs again, its newest release")
    .option("--name <app>")
    .action(async (flags) => ctx.io.result(await service.startApp(ctx, service.appName(ctx, flags.name)), render.started));
  deploy
    .command("rm")
    .description("stop hosting the app: its releases go, and its token is revoked")
    .option("--name <app>")
    .action(async (flags) => ctx.io.result(await service.removeApp(ctx, service.appName(ctx, flags.name)), render.removed));
}

/** The release followed until it is live (0), failed or replaced (1), or the time is up (1). */
async function follow(ctx: Context, sent: service.Release | { name: string; release: number }): Promise<void> {
  ctx.io.info(render.following(sent.name));
  const said = await service.followRelease(ctx, sent.name, sent.release, service.FOLLOW_WITHIN_MS);
  ctx.io.info(render.settled(said, sent.release, service.FOLLOW_WITHIN_MS));
  if (said?.live !== true) throw new PinecallError(`release ${sent.release} is not live`);
}
