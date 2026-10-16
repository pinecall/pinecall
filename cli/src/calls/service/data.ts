/** The org's data: erasures and their trail, who read what, the policy, consent, the do-not-call list, export. */

import { dirname } from "node:path";
import { createWriteStream, existsSync } from "node:fs";
import { readFileSync } from "node:fs";
import { Readable, type Writable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { ReadableStream as WebStream } from "node:stream/web";

import { z } from "zod";

import * as api from "../../api/compliance.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";

export type { ConsentHistory, DoNotCall, DoNotCallImported, Erasure, ErasureTrail, OrgPolicy, OrgPolicyRow, Reads } from "../../api/compliance.js";

export const SAY_YES = (what: string, who: string): string => `erasing ${what} ${who} cannot be undone: run it again with --yes`;
const ONE_OR_THE_OTHER = (a: string, b: string): string => `${a} and ${b} say two things about one field`;
const ONE_DISCLOSURE = "one of --disclosure '<your words>', --platform-disclosure or --no-disclosure";
const HOURS = /^(\d{1,2})-(\d{1,2})$/;
const DAYS = { error: "--retention-days takes a whole number of days, 1 or more; --keep-all keeps every call" };
const PER_DAY = { error: "--per-number-day takes a whole number of calls, 1 or more; --no-per-number lifts it" };

/** What `data policy` takes: each flag one field; the rest stay. */
export const PolicyInput = z.object({
  retentionDays: z.number(DAYS).int(DAYS).min(1, DAYS).optional(),
  keepAll: z.boolean().default(false),
  callingHours: z.string().regex(HOURS, "two hours of the day, from-until, like 9-20").optional(),
  anyHours: z.boolean().default(false),
  perNumberDay: z.number(PER_DAY).int(PER_DAY).min(1, PER_DAY).optional(),
  noPerNumber: z.boolean().default(false),
  consentEverywhere: z.boolean().default(false),
  consentByLaw: z.boolean().default(false),
  disclosure: z.string().optional(),
  platformDisclosure: z.boolean().default(false),
  noDisclosure: z.boolean().default(false),
  recordingNotice: z.boolean().default(false),
  noRecordingNotice: z.boolean().default(false),
});
export type PolicyInput = z.infer<typeof PolicyInput>;

/** What `data consent` takes: the number, and a consent given, or an opt-out. */
export const ConsentInput = z.object({
  number: z.string().min(1),
  give: z.enum(["express", "written"]).optional(),
  source: z.string().optional(),
  text: z.string().optional(),
  evidence: z.string().optional(),
  optOut: z.boolean().default(false),
});
export type ConsentInput = z.infer<typeof ConsentInput>;

export async function eraseCall(ctx: Context, call: string): Promise<api.Erasure> {
  return api.eraseCall(ctx.gateway(), call);
}

export async function eraseContact(ctx: Context, contact: string): Promise<api.Erasure> {
  return api.eraseContact(ctx.gateway(), contact);
}

export async function listErasures(ctx: Context): Promise<api.ErasureTrail> {
  return api.listErasures(ctx.gateway());
}

export async function listReads(ctx: Context, subject?: string): Promise<api.Reads> {
  return api.listReads(ctx.gateway(), subject);
}

/** The policy read, or one field changed and the row written back whole. */
export async function policy(ctx: Context, input: PolicyInput): Promise<api.OrgPolicyRow> {
  const changes = changesOf(input);
  const gw = ctx.gateway();
  const kept = await api.getPolicy(gw);
  if (Object.keys(changes).length === 0) return kept;
  return api.putPolicy(gw, { ...kept.policy, ...changes });
}

/** What stands for a number; a consent given, or the number put on the do-not-call list. */
export async function consent(ctx: Context, input: ConsentInput): Promise<api.ConsentHistory> {
  const gw = ctx.gateway();
  if (input.give !== undefined && input.optOut) throw new UsageError("--give and --opt-out say two things about one number");
  if (input.give === undefined && (input.source !== undefined || input.text !== undefined || input.evidence !== undefined)) {
    throw new UsageError("--source, --text and --evidence go with --give express|written");
  }
  if (input.optOut) return api.optOut(gw, input.number);
  if (input.give === undefined) return api.getConsent(gw, input.number);
  const source = (input.source ?? "").trim();
  if (source === "") throw new UsageError("--give needs --source: where the consent came from, a form, a call, a signed paper");
  return api.giveConsent(gw, { number: input.number, kind: input.give, source, text: input.text ?? null, evidence: input.evidence ?? null });
}

export async function listDoNotCall(ctx: Context, after?: string): Promise<api.DoNotCall> {
  return api.listDoNotCall(ctx.gateway(), after);
}

export async function addDoNotCall(ctx: Context, numbers: string[], source: string): Promise<api.DoNotCallImported> {
  if (numbers.length === 0 || source.trim() === "") throw new UsageError("dnc add takes the numbers and --source '…'");
  return api.addDoNotCall(ctx.gateway(), numbers, source.trim());
}

/** A file of numbers, one a line, put on the list; read before the gateway is asked. */
export async function importDoNotCall(ctx: Context, file: string, source: string): Promise<api.DoNotCallImported> {
  const numbers = readFileSync(file, "utf8").split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== "");
  if (numbers.length === 0) throw new UsageError(`nothing in ${file}: one number a line`);
  return addDoNotCall(ctx, numbers, source);
}

/** The org's env whole as JSON Lines, into a file or a stream; the file's path when one was written. */
export async function exportOrg(ctx: Context, into: string | Writable): Promise<{ file: string | null }> {
  const body = await api.exportOrg(ctx.gateway());
  if (body === null) return { file: null };
  const stream = Readable.fromWeb(body as WebStream<Uint8Array>);
  if (typeof into === "string") {
    if (!existsSync(dirname(into))) throw new UsageError(`cannot write ${into}: no folder ${dirname(into)}`);
    await pipeline(stream, createWriteStream(into));
    return { file: into };
  }
  await pipeline(stream, into, { end: false });
  return { file: null };
}

/** "9-20" as from and until, or undefined when it is no window of the day. */
export function hoursOf(said: string): { from: number; until: number } | undefined {
  const found = HOURS.exec(said);
  if (found === null) return undefined;
  const from = Number(found[1]);
  const until = Number(found[2]);
  return from >= 0 && from <= 23 && until >= 1 && until <= 24 && from < until ? { from, until } : undefined;
}

// The fields the flags change; an empty object reads the policy.
function changesOf(input: PolicyInput): Partial<api.OrgPolicy> {
  if (input.retentionDays !== undefined && input.keepAll) throw new UsageError(ONE_OR_THE_OTHER("--retention-days", "--keep-all"));
  if (input.callingHours !== undefined && input.anyHours) throw new UsageError(ONE_OR_THE_OTHER("--calling-hours", "--any-hours"));
  if (input.perNumberDay !== undefined && input.noPerNumber) throw new UsageError(ONE_OR_THE_OTHER("--per-number-day", "--no-per-number"));
  if (input.consentEverywhere && input.consentByLaw) throw new UsageError(ONE_OR_THE_OTHER("--consent-everywhere", "--consent-by-law"));
  if (input.recordingNotice && input.noRecordingNotice) throw new UsageError(ONE_OR_THE_OTHER("--recording-notice", "--no-recording-notice"));
  const disclosures = [input.disclosure !== undefined, input.platformDisclosure, input.noDisclosure].filter(Boolean).length;
  if (disclosures > 1 || (input.disclosure !== undefined && input.disclosure.trim() === "")) throw new UsageError(ONE_DISCLOSURE);
  const changes: Partial<api.OrgPolicy> = {};
  if (input.keepAll) changes.retention_days = null;
  if (input.retentionDays !== undefined) changes.retention_days = input.retentionDays;
  if (input.anyHours) changes.calling_hours = null;
  if (input.callingHours !== undefined) {
    const hours = hoursOf(input.callingHours);
    if (hours === undefined) throw new UsageError(`--calling-hours ${input.callingHours}: two hours of the day, from-until, like 9-20`);
    changes.calling_hours = hours;
  }
  if (input.noPerNumber) changes.per_number_day = null;
  if (input.perNumberDay !== undefined) changes.per_number_day = input.perNumberDay;
  if (input.consentEverywhere) changes.consent_everywhere = true;
  if (input.consentByLaw) changes.consent_everywhere = false;
  if (input.disclosure !== undefined) changes.disclosure = input.disclosure.trim();
  if (input.platformDisclosure) changes.disclosure = null;
  if (input.noDisclosure) changes.disclosure = "";
  if (input.recordingNotice) changes.recording_notice = true;
  if (input.noRecordingNotice) changes.recording_notice = false;
  return changes;
}
