/** The operator's doors for telephony: carriers and the fence, networks orgs asked for, every number, the numbers account, the test line, and a number's traceback. */

import { z } from "zod";

import { drop, GatewayError, post, put, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";

// Loose on purpose, every one: a field the gateway adds never breaks the operator's page.

// ── carriers and the fence ──────────────────────────────────────────────────────

const CarrierSchema = z.looseObject({
  kind: z.string(),
  name: z.string(),
  /** The deployment drives the carrier's API; without it an org pastes one SIP address in the carrier's portal. */
  control: z.boolean(),
  networks: z.array(z.string()),
  source: z.string(),
  read_on: z.string(),
  admitted: z.boolean(),
  /** The deployment's own carrier, admitted always. */
  fixed: z.boolean(),
  /** The numbers of every org that come through it. */
  numbers: z.number(),
});
export type CatalogCarrier = z.infer<typeof CarrierSchema>;

const FenceSchema = z.looseObject({
  /** What is let in beyond the admitted carriers' own networks, each with why. */
  openings: z.array(z.looseObject({ network: z.string(), reason: z.string() })),
  /** Every network the firewall should admit. */
  networks: z.array(z.string()),
});
export type Fence = z.infer<typeof FenceSchema>;

const CarriersSchema = z.looseObject({ carriers: z.array(CarrierSchema), fence: FenceSchema });
export type Carriers = z.infer<typeof CarriersSchema>;

export async function readCarriers(credentials: Credentials): Promise<Carriers> {
  return CarriersSchema.parse(await read(credentials, `${OPS}/carriers`));
}

/** Admit a carrier of the catalog, or stop; the deployment's own is refused off. */
export async function admitCarrier(credentials: Credentials, kind: string, admitted: boolean): Promise<void> {
  await put(credentials, `${OPS}/carriers/${encodeURIComponent(kind)}`, { admitted });
}

// ── networks an org asked to be let in from ─────────────────────────────────────

const AskSchema = z.looseObject({
  id: z.number(),
  /** The org's slug. */
  org: z.string(),
  /** What the org asked it for: the name of its PBX account, or of the number it hooked. */
  source: z.string(),
  network: z.string(),
  state: z.string(),
  asked_at: z.number(),
  decided_by: z.string().nullish(),
  decided_at: z.number().nullish(),
});
export type Ask = z.infer<typeof AskSchema>;

/** Every network an org asked for, oldest first, answered or not. */
export async function readAsks(credentials: Credentials): Promise<Ask[]> {
  return z.array(AskSchema).parse(await read(credentials, `${OPS}/carrier-networks`));
}

/** Answer one; the org's trunks follow at once. */
export async function answerAsk(credentials: Credentials, ask: number, answer: "approve" | "refuse"): Promise<void> {
  await post(credentials, `${OPS}/carrier-networks/${ask}/${answer}`, {});
}

// ── every number ────────────────────────────────────────────────────────────────

const BoxNumberSchema = z.looseObject({
  number: z.string(),
  channel: z.string(),
  /** The org's slug. */
  org: z.string(),
  env: z.string(),
  agent: z.string(),
  /** bought, twilio, sip, whatsapp, imported, hooked or typed. */
  came_in: z.string(),
  /** A process holds the agent now, so a call is picked up. */
  running: z.boolean(),
  /** False while a number the org hooked itself waits for the operator. */
  approved: z.boolean(),
  /** The catalog carrier a hooked number comes through. */
  via: z.string().nullish(),
});
export type BoxNumber = z.infer<typeof BoxNumberSchema>;

/** Every number of the deployment, every org and both environments. */
export async function readBoxNumbers(credentials: Credentials): Promise<BoxNumber[]> {
  return z.array(BoxNumberSchema).parse(await read(credentials, `${OPS}/numbers`));
}

/** Let a number an org hooked ring. */
export async function approveNumber(credentials: Credentials, number: string, org: string): Promise<void> {
  await post(credentials, `${OPS}/numbers/${encodeURIComponent(number)}/approve?org=${encodeURIComponent(org)}`, {});
}

/** Refuse a number an org hooked: its row is let go of, and it never rings here. */
export async function refuseNumber(credentials: Credentials, number: string, org: string): Promise<void> {
  await drop(credentials, `${OPS}/routes/${encodeURIComponent(number)}?org=${encodeURIComponent(org)}`);
}

// ── the account the deployment buys numbers on ──────────────────────────────────

const NumbersAccountSchema = z.looseObject({ account_sid: z.string(), label: z.string().nullish() });
export type NumbersAccount = z.infer<typeof NumbersAccountSchema>;

/** The Twilio account numbers are bought on, never its secret; null when there is none, and then no number is sold. */
export async function readNumbersAccount(credentials: Credentials): Promise<NumbersAccount | null> {
  try {
    return NumbersAccountSchema.parse(await read(credentials, `${OPS}/numbers-account`));
  } catch (refused) {
    if (refused instanceof GatewayError && refused.status === 404) return null;
    throw refused;
  }
}

/** Keep the account: the gateway tries it with Twilio first, and one Twilio refuses is never kept. */
export async function saveNumbersAccount(credentials: Credentials, wanted: { account_sid: string; user: string; secret: string; label: string }): Promise<void> {
  await put(credentials, `${OPS}/numbers-account`, wanted);
}

export async function dropNumbersAccount(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/numbers-account`);
}

// ── the test line ───────────────────────────────────────────────────────────────

/** The sandbox number a person calls from their own phone to reach their own agent; null with none. */
export async function readTestLine(credentials: Credentials): Promise<string | null> {
  return z.looseObject({ number: z.string().nullish() }).parse(await read(credentials, `${OPS}/test-line`)).number ?? null;
}

/** Make a number routed in the sandbox the test line; null forgets it. */
export async function saveTestLine(credentials: Credentials, number: string | null): Promise<void> {
  await put(credentials, `${OPS}/test-line`, { number });
}

// ── traceback ───────────────────────────────────────────────────────────────────

const TracedCallSchema = z.looseObject({
  call: z.string(),
  /** The org's id, not its slug. */
  org: z.string().nullish(),
  env: z.string().nullish(),
  direction: z.string().nullish(),
  from_number: z.string().nullish(),
  to_number: z.string().nullish(),
  started_at: z.number().nullish(),
  ended_at: z.number().nullish(),
  end_reason: z.string().nullish(),
  /** The call was erased: only its detail record is left. */
  erased: z.boolean(),
});
export type TracedCall = z.infer<typeof TracedCallSchema>;

const TracedDialSchema = z.looseObject({
  org: z.string(),
  env: z.string(),
  agent: z.string(),
  call: z.string().nullish(),
  /** The number the person called saw. */
  shown: z.string().nullish(),
  asked_by: z.string(),
  /** Why it was not placed; null when it was. */
  refused: z.string().nullish(),
  at: z.number(),
});
export type TracedDial = z.infer<typeof TracedDialSchema>;

const TracebackSchema = z.looseObject({ number: z.string(), since: z.number(), calls: z.array(TracedCallSchema), dials: z.array(TracedDialSchema) });
export type Traceback = z.infer<typeof TracebackSchema>;

/** A number's phone calls in every org, kept or erased, and every dial to it; 24 months back unless `since` says less. */
export async function readTraceback(credentials: Credentials, number: string, since: number | null): Promise<Traceback> {
  return TracebackSchema.parse(await read(credentials, `${OPS}/traceback`, since === null ? { number } : { number, since }));
}
