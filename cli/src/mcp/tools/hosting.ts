/** The `deploy` tool: the hosting domain, over its service. */

import { z } from "zod";

import * as service from "../../hosting/service.js";
import { tool, ToolRefused, type ToolContext } from "../tool.js";
import { WAIT, WAIT_S } from "./fields.js";

export const deploy = tool({
  name: "deploy",
  description: "Run the project on Pinecall: a release uploaded and followed until live; the apps, their releases, their logs, a rollback, stop and start.",
  schema: {
    action: z.enum(["deploy", "wait", "list", "releases", "logs", "rollback", "stop", "start"]).describe("deploy uploads the project as a release; wait follows one further; list the org's apps; releases of one app; logs of its process; rollback sends a release's sources again; stop and start its process"),
    name: z.string().optional().describe("the app's name; the project folder's when left out"),
    note: z.string().optional().describe("`deploy`: a note kept with the release"),
    release: z.number().int().min(1).optional().describe("`wait`: the release to wait for; `rollback`: the release whose sources are sent again"),
    wait_s: WAIT,
  },
  manual:
    "`deploy` uploads the project as a release — what its `.gitignore` files leave in, never `node_modules`, `.git`, `dist` or any `.env` — and Pinecall installs it and starts its agents; the release before keeps answering until the new one's agents register, so no call is cut. It follows the release for `wait_s` and answers whether it is live or why it failed; `wait` follows it further. `logs` reads the app's last lines. TypeScript projects only. Removing an app is never a tool: `pinecall deploy rm` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "list") return { apps: await service.listApps(ctx) };
    const name = service.appName(ctx, args.name);
    const waitS = args.wait_s ?? WAIT_S;
    switch (args.action) {
      case "releases":
        return { releases: await service.listReleases(ctx, name) };
      case "logs":
        return await service.readLogs(ctx, name, service.LOGS_WITHIN_MS);
      case "stop":
        return { app: name, stopped: (await service.stopApp(ctx, name)) !== undefined };
      case "start":
        return { app: name, started: (await service.startApp(ctx, name)) !== undefined };
      case "rollback": {
        if (args.release === undefined) throw new ToolRefused("rollback takes the release whose sources are sent again: `releases` lists them");
        const again = await service.rollbackRelease(ctx, name, args.release);
        return { sent: again.release, ...(await followed(ctx, name, again.release, waitS)) };
      }
      case "wait":
        if (args.release === undefined) throw new ToolRefused("wait takes the release to follow: the one `deploy` answered");
        return await followed(ctx, name, args.release, waitS);
      default: {
        const sent = await service.uploadRelease(ctx, name, args.note ?? "");
        return { app: name, release: sent.release, bytes: sent.bytes, sha256: sent.sha256, ...(await followed(ctx, name, sent.release, waitS)) };
      }
    }
  },
});

// The release followed until it is live, failed or replaced, or the wait is up: then `wait` follows it further.
async function followed(ctx: ToolContext, name: string, release: number, waitS: number): Promise<Record<string, unknown>> {
  const said = await service.followRelease(ctx, name, release, waitS * 1000);
  if (said !== null) return { live: said.live, said: said.line };
  return { live: false, waiting: true, says: `release ${release} is not live yet: call deploy with action wait and release ${release}` };
}
