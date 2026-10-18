/** Signing this machine in: a pairing opened at the gateway, the key collected once a person approves it, proved and kept. */

import { z } from "zod";

import * as api from "../../api/accounts.js";
import type { GatewayClient } from "../../api/client.js";
import type { Context } from "../../context.js";
import { Cancelled, errorMessage, PinecallError } from "../../errors.js";
import { hostname } from "../../kit/hostname.js";
import { CLOUD_URL } from "../../project/credentials.js";
import { homeOf } from "../../kit/home.js";
import { keepSignIn, readSignIn, type MachineSignIn } from "../../project/session.js";
import { orgOf, personOf } from "./whoami.js";

// The pairing code expires after ten minutes; stop asking shortly after. Each ask is held by the
// gateway until a person approves or this many seconds pass, the most it holds one.
const WAIT_S = 25;
const GIVE_UP_MS = 11 * 60 * 1_000;

export const TOOK_TOO_LONG = "nobody approved this terminal: `pinecall login` again when you are ready";

/** What a sign-in takes: the gateway, and how patiently the key is waited for (tests shorten it). */
export const StartSignInInput = z.object({
  gateway: z.string().url().default(CLOUD_URL),
  /** How long the gateway holds each ask for the key, seconds. */
  waitS: z.number().positive().default(WAIT_S),
  /** How long to keep asking before giving up, milliseconds. */
  untilMs: z.number().positive().default(GIVE_UP_MS),
});
export type StartSignInInput = z.infer<typeof StartSignInInput>;

/** This machine, signed in: the gateway, the person the gateway says the key is, and the org it acts in. Never the key. */
export interface SignedIn {
  gateway: string;
  name: string;
  org: string;
}

/** A sign-in in flight: the link a person opens, and the outcome once they did. */
export interface SignIn {
  readonly gateway: string;
  readonly link: string;
  /** The person, once they approved it; rejects when the code died or nobody came in time. */
  readonly done: Promise<SignedIn>;
  /** How it ended, for a caller that looks in rather than waits (the MCP server); unset while in flight. */
  outcome?: SignedIn | { failed: string };
}

/** The machine's sign-in at the gateway named, else at the last one used; undefined when it is not signed in. */
export function machineSignIn(ctx: Context, gateway?: string): MachineSignIn | undefined {
  return readSignIn(homeOf(ctx.processEnv), gateway);
}

/**
 * Open a pairing on the gateway: the link carries only a one-time code that dies in ten minutes.
 * The key is collected in the background, proved by asking who it is, and kept as the machine's sign-in
 * only then, so a broken key is never saved. The caller shows the link; nothing here opens a browser.
 */
export async function startSignIn(ctx: Context, input: StartSignInInput): Promise<SignIn> {
  const url = input.gateway.replace(/\/$/, "");
  const gw = api.accountsGateway(url);
  const code = await api.createPairing(gw, hostname());
  const signIn: SignIn = {
    gateway: url,
    link: signInLink(url, code),
    done: collectKey(ctx, gw, code, input).then(async (key) => {
      const who = await api.getWhoami(api.accountsGateway(url, key));
      keepSignIn(homeOf(ctx.processEnv), url, key, orgOf(who));
      return { gateway: url, name: personOf(who), org: orgOf(who) };
    }),
  };
  // Recorded here so a rejection nobody awaited yet is handled, and so `outcome` can be read later.
  signIn.done.then(
    (signed) => void (signIn.outcome = signed),
    (failed: unknown) => void (signIn.outcome = { failed: errorMessage(failed) }),
  );
  return signIn;
}

/** The gateway's sign-in page for a pairing code. */
export function signInLink(gateway: string, code: string): string {
  return `${gateway.replace(/\/$/, "")}/cli?c=${encodeURIComponent(code)}`;
}

// 202 with no key means nobody approved within the wait; a refusal means the code was collected or expired.
async function collectKey(ctx: Context, gw: GatewayClient, code: string, input: StartSignInInput): Promise<string> {
  const until = Date.now() + input.untilMs;
  while (Date.now() < until) {
    const askedAt = Date.now();
    let key: string | undefined;
    try {
      key = await api.getPairingKey(gw, code, input.waitS, ctx.signal);
    } catch (failed) {
      if (ctx.signal.aborted) throw new Cancelled();
      throw failed;
    }
    if (key !== undefined) return key;
    // A 202 before the wait is up (a proxy that cut the hold) is not an invitation to ask at once.
    const owed = input.waitS * 1000 - (Date.now() - askedAt);
    if (owed > 0) await new Promise((rung) => setTimeout(rung, Math.min(owed, until - Date.now())));
  }
  throw new PinecallError(TOOK_TOO_LONG);
}
