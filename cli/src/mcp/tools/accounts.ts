/** The `login`, `link` and `whoami` tools: the accounts domain, over its service. */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

import * as service from "../../accounts/service/index.js";
import { DOTENV } from "../../kit/dotenv.js";
import { CLOUD_URL } from "../../project/credentials.js";
import { tool, ToolRefused } from "../tool.js";
import { WAIT, WAIT_S } from "./fields.js";

export const NOT_SIGNED_IN = "this machine is not signed in: call `login` with action start, and the person opens the link it answers";

export const login = tool({
  name: "login",
  description: "Sign this machine in to Pinecall: `start` returns a link for the person to open; `status` waits for their approval.",
  schema: {
    action: z.enum(["start", "status"]).describe("start opens a sign-in and answers its link; status waits for the person to approve it"),
    gateway: z.string().url().optional().describe("the gateway to sign in to; Pinecall Cloud when left out"),
    wait_s: WAIT,
  },
  manual:
    "`login` signs this machine in, once: `start` answers a link — show it to the person, who signs in there, in a browser, where a password belongs — then call `status` until it says signed in. No password and no key ever passes through you. Then `link` writes the project's key.",
  handler: async (args, ctx) => {
    if (args.action === "start") {
      const signIn = await service.startSignIn(ctx, service.StartSignInInput.parse({ gateway: args.gateway ?? CLOUD_URL }));
      ctx.session.signIn = signIn;
      return { link: signIn.link, says: "Show the person this link to sign in, then call login with action status." };
    }
    const signIn = ctx.session.signIn;
    if (signIn === undefined) return { signed_in: false, says: "nothing in flight: call login with action start" };
    let timer: NodeJS.Timeout | undefined;
    await Promise.race([signIn.done.catch(() => undefined), new Promise((rung) => (timer = setTimeout(rung, (args.wait_s ?? WAIT_S) * 1000)))]);
    clearTimeout(timer);
    const outcome = signIn.outcome;
    if (outcome === undefined) return { signed_in: false, waiting: true, link: signIn.link };
    if ("failed" in outcome) return { signed_in: false, refused: outcome.failed };
    return { signed_in: true, gateway: outcome.gateway, as: outcome.name };
  },
});

export const link = tool({
  name: "link",
  description: "List the person's orgs (`orgs`), or write the key of one of them into the open project's .env (`write`).",
  schema: {
    action: z.enum(["orgs", "write"]).describe("orgs lists the person's orgs; write mints their key in one and writes it into the project's .env"),
    org: z.string().optional().describe("the org's slug, for `write`; may be left out when the person has one org"),
  },
  manual:
    "`link` ties the open project to an org, once a machine is signed in (`login`): `orgs` lists them, `write` mints the person's key in the chosen one and writes it into the project's .env, which every other tool reads. The key itself never comes back to you.",
  handler: async (args, ctx) => {
    const machine = service.machineSignIn(ctx);
    if (machine === undefined) throw new ToolRefused(NOT_SIGNED_IN);
    const orgs = await service.listOrgs(ctx, machine);
    if (args.action === "orgs") return { orgs: orgs.map((org) => ({ slug: service.slugOf(org), this_machines: org.here })) };
    const linked = await service.linkProject(ctx, machine, service.chooseOrg(orgs, args.org));
    return { org: linked.org, written: linked.written, file: linked.file, ...gitIgnores(ctx.cwd) };
  },
});

export const whoami = tool({
  name: "whoami",
  description: "Which org, gateway and environment the open project's key acts in, and whether production is allowed.",
  schema: {},
  manual:
    "`whoami` first, in any session: it proves the project's key and names the org. Refused with a sentence naming `link` when the project has no key yet; with `prod`, it says whether the key may act in production.",
  handler: async (_args, ctx) => {
    const who = await service.getWhoami(ctx);
    const { url, source } = ctx.credentials();
    return {
      org: service.orgOf(who),
      gateway: url,
      environment: ctx.env,
      key_from: source,
      person: who.name ?? who.label ?? null,
      production_allowed_for_this_key: who.production === true,
    };
  },
});

// No git is asked (the server starts no process): the project's own .gitignore is read instead.
function gitIgnores(root: string): { warning?: string } {
  const ignore = join(root, ".gitignore");
  const named = existsSync(ignore) && readFileSync(ignore, "utf8").split("\n").some((line) => [DOTENV, ".env*", ".env.*"].includes(line.trim()));
  return named ? {} : { warning: `${DOTENV} holds the key and .gitignore does not name it: add it before a commit carries the key` };
}
