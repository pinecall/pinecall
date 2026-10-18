/** The `login`, `whoami` and `team` tools: the accounts domain, over its service. */

import { z } from "zod";

import * as service from "../../accounts/service/index.js";
import { CLOUD_URL } from "../../project/credentials.js";
import { tool, ToolRefused } from "../tool.js";
import { needed, WAIT, WAIT_S } from "./fields.js";

export const NOT_SIGNED_IN = "this machine is not signed in: call `login` with action start, and the person opens the link it answers";

export const login = tool({
  name: "login",
  description: "Sign this machine in to a gateway: `start` returns a link for the person to open; `status` waits for their approval.",
  schema: {
    action: z.enum(["start", "status"]).describe("start opens a sign-in and answers its link; status waits for the person to approve it"),
    gateway: z.string().url().optional().describe("the gateway to sign in to; Pinecall Cloud when left out"),
    wait_s: WAIT,
  },
  manual:
    "`login` signs this machine in, once per gateway: `start` answers a link — show it to the person, who signs in there, in a browser, where a password belongs — then call `status` until it says signed in. Every tool runs on that sign-in, in the org the project's pinecall.json names; the person may belong to several. No password and no key ever passes through you. A runtime on this machine (`runtime` up) signs it in by itself.",
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
    return { signed_in: true, gateway: outcome.gateway, as: outcome.name, org: outcome.org };
  },
});

export const whoami = tool({
  name: "whoami",
  description: "Which org, gateway and environment the open project's key acts in, and whether production is allowed.",
  schema: {},
  manual:
    "`whoami` first, in any session: it proves the project's key and names the org. Refused with a sentence naming `login` when this machine is signed in nowhere; with `prod`, it says whether the key may act in production.",
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

export const team = tool({
  name: "team",
  description: "The org's people (`list`), or a one-use link that lets one of them choose a new password (`reset`).",
  schema: {
    action: z.enum(["list", "reset"]).describe("list the org's people; reset makes a one-use link for one of them to choose their password"),
    email: z.string().optional().describe("reset: the person's address"),
  },
  manual:
    "`team` lists the org's people, and for `reset` answers a one-use link the person opens to choose their own password: no password ever passes through you. Show the link to that person alone. Setting a password directly is `pinecall team password <email>` in a terminal, where it is typed without echo.",
  reveals: (result) => {
    const link = (result as { link?: unknown }).link;
    return typeof link === "string" ? [link] : [];
  },
  handler: async (args, ctx) => {
    if (args.action === "list") return { people: (await service.listTeam(ctx)).map(({ email, name, role, status, operator }) => ({ email, name, role, status, runs_the_box: operator })) };
    const reset = await service.resetLink(ctx, needed(args.email, "email"));
    return reset.link !== null
      ? { email: reset.email, link: reset.link, says: "Give this link to that person alone: it works once, and they choose their password there." }
      : { email: reset.email, mailed: reset.mailed, says: reset.mailed ? "They were mailed a one-use link." : "No link was handed over: `pinecall team password` in a terminal sets it." };
  },
});
