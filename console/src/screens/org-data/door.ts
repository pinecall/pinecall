/** The data doors: the org's policy, its erasure trail, a contact or a call erased, the export. */

import { z } from "zod";

import { drop, headersFor, post, put, read, doorUrl, GatewayError, type Credentials } from "@pinecall/core/api";

const ErasureSchema = z.object({
  id: z.number(),
  at: z.number(),
  what: z.enum(["call", "contact", "org", "agent"]),
  subject: z.string(),
  env: z.enum(["production", "sandbox"]).nullable(),
  asked_by: z.string(),
  calls: z.number(),
  entries: z.number(),
  memories: z.number(),
  recordings: z.number(),
});

/** What one erasure took, as the trail says it. */
export type Erasure = z.infer<typeof ErasureSchema>;

const TrailSchema = z.object({ erasures: z.array(ErasureSchema) });

const PolicySchema = z.object({
  retention_days: z.number().nullish(),
  calling_hours: z.object({ from: z.number(), until: z.number() }).nullish(),
  per_number_day: z.number().nullish(),
  consent_everywhere: z.boolean().nullish(),
  disclosure: z.string().nullish(),
  recording_notice: z.boolean().nullish(),
});

/** The org's compliance settings: retention, calling rules, consent, what a call says first. */
export type Policy = z.infer<typeof PolicySchema>;

/** The policy of an org nobody set: the platform's defaults. */
export const NOTHING_SET: Policy = { retention_days: null, calling_hours: null, per_number_day: null, consent_everywhere: false, disclosure: null, recording_notice: true };

const PolicyRowSchema = z.object({
  policy: PolicySchema,
  set_by: z.string().nullable(),
  set_at: z.number().nullable(),
});

/** The policy, and who set it last. */
export type PolicyRow = z.infer<typeof PolicyRowSchema>;

/** `GET /v1/org/policy`. */
export async function readPolicy(credentials: Credentials): Promise<PolicyRow> {
  return PolicyRowSchema.parse(await read(credentials, "/v1/org/policy"));
}

// The gateway replaces the row whole: a field changed is the row read and written back.
/** `PUT /v1/org/policy` with the row as kept and these fields changed. */
export async function putPolicy(credentials: Credentials, kept: Policy, changes: Partial<Policy>): Promise<PolicyRow> {
  return PolicyRowSchema.parse(await put(credentials, "/v1/org/policy", { ...kept, ...changes }));
}

/** `GET /v1/org/erasures`, newest first. */
export async function readTrail(credentials: Credentials): Promise<Erasure[]> {
  return TrailSchema.parse(await read(credentials, "/v1/org/erasures")).erasures;
}

const ReadSchema = z.object({
  subject: z.string(),
  // runtime wire/rest/calls.py: ReadKind — every read is on the record, so every kind is here.
  what: z.enum(["log", "recording", "traceback", "listen", "supervise", "export", "memory"]),
  env: z.enum(["production", "sandbox"]).nullable(),
  reader: z.string(),
  at: z.number(),
});

/** One read of the org's data: the call or number, what of it, who, when. */
export type Read = z.infer<typeof ReadSchema>;

/** `GET /v1/org/reads`, newest first; of one call or number when named. */
export async function readReads(credentials: Credentials, subject: string | null): Promise<Read[]> {
  const query: Record<string, string> = subject === null ? {} : { subject };
  return z.object({ reads: z.array(ReadSchema) }).parse(await read(credentials, "/v1/org/reads", query)).reads;
}

/** `DELETE /v1/contacts/{contact}`: every call they were on in this world, and every fact kept of them. */
export async function eraseContact(credentials: Credentials, contact: string): Promise<Erasure> {
  return ErasureSchema.parse(await drop(credentials, `/v1/contacts/${encodeURIComponent(contact)}`));
}

/** `DELETE /v1/calls/{call}`: one ended call, its log, facts, memories and recording. */
export async function eraseCall(credentials: Credentials, call: string): Promise<Erasure> {
  return ErasureSchema.parse(await drop(credentials, `/v1/calls/${encodeURIComponent(call)}`));
}

// A download needs the key in a header, which a plain link cannot carry: the lines are fetched
// through the gateway's own URL and handed to the browser as a file.
/** `GET /v1/org/export`, as a file the browser saves. */
export async function exportWorld(credentials: Credentials): Promise<{ file: Blob; name: string }> {
  const answer = await fetch(doorUrl(credentials, "/v1/org/export"), { headers: headersFor(credentials) });
  if (!answer.ok) throw new GatewayError(answer.status, await answer.text());
  const disposition = answer.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "pinecall-export.jsonl";
  return { file: await answer.blob(), name };
}

const ConsentHistorySchema = z.object({
  number: z.string(),
  standing: z.enum(["consented", "opted_out", "unknown"]),
  rows: z.array(
    z.object({
      kind: z.enum(["express", "written", "opt_out"]),
      source: z.string(),
      text: z.string().nullable(),
      evidence: z.string().nullable(),
      given_by: z.string(),
      call: z.string().nullable(),
      given_at: z.number(),
    }),
  ),
});

/** What stands for a number, and every fact about it, newest first. */
export type ConsentHistory = z.infer<typeof ConsentHistorySchema>;

const DoNotCallSchema = z.object({
  numbers: z.array(z.object({ number: z.string(), since: z.number(), source: z.string(), given_by: z.string() })),
  next: z.string().nullable(),
});

/** A page of the do-not-call list. */
export type DoNotCall = z.infer<typeof DoNotCallSchema>;

const ImportedSchema = z.object({ added: z.number(), refused: z.array(z.string()) });

/** `GET /v1/org/consents/{number}`. */
export async function readConsent(credentials: Credentials, number: string): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await read(credentials, `/v1/org/consents/${encodeURIComponent(number)}`));
}

/** `POST /v1/org/consents`: a consent given, express or written, with where it came from. */
export async function giveConsent(
  credentials: Credentials,
  given: { number: string; kind: "express" | "written"; source: string; text: string | null },
): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await post(credentials, "/v1/org/consents", given));
}

/** `DELETE /v1/org/consents/{number}`: the number onto the do-not-call list. */
export async function optOut(credentials: Credentials, number: string): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await drop(credentials, `/v1/org/consents/${encodeURIComponent(number)}`));
}

/** `GET /v1/org/dnc`, a page after the cursor. */
export async function readDoNotCall(credentials: Credentials, after: string | null): Promise<DoNotCall> {
  return DoNotCallSchema.parse(await read(credentials, "/v1/org/dnc", after === null ? {} : { after }));
}

/** `POST /v1/org/dnc`: numbers onto the list at once, and the lines that were no number. */
export async function importDoNotCall(credentials: Credentials, numbers: string[], source: string): Promise<{ added: number; refused: string[] }> {
  return ImportedSchema.parse(await post(credentials, "/v1/org/dnc", { numbers, source }));
}
