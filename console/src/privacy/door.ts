/** The privacy doors: the org's policy, consent and the do-not-call list, the export, an erasure and the trail, and who read what. */

import { z } from "zod";

import { drop, doorUrl, GatewayError, headersFor, post, put, read, type Credentials } from "@pinecall/core/api";

const PolicySchema = z.looseObject({
  retention_days: z.number().nullish(),
  calling_hours: z.looseObject({ from: z.number(), until: z.number() }).nullish(),
  per_number_day: z.number().nullish(),
  consent_everywhere: z.boolean().nullish(),
  disclosure: z.string().nullish(),
  recording_notice: z.boolean().nullish(),
});

/** Retention, the calling rules, consent, and what a call says first. */
export type Policy = z.infer<typeof PolicySchema>;

const PolicyRowSchema = z.looseObject({ policy: PolicySchema, set_by: z.string().nullish(), set_at: z.number().nullish() });

/** The policy, and who set it last. */
export type PolicyRow = z.infer<typeof PolicyRowSchema>;

/** `GET /v1/org/policy`. */
export async function readPolicy(credentials: Credentials): Promise<PolicyRow> {
  return PolicyRowSchema.parse(await read(credentials, "/v1/org/policy"));
}

// The gateway replaces the row whole: what was read goes back, with the change over it.
/** `PUT /v1/org/policy`. */
export async function putPolicy(credentials: Credentials, kept: Policy, changes: Partial<Policy>): Promise<PolicyRow> {
  return PolicyRowSchema.parse(await put(credentials, "/v1/org/policy", { ...kept, ...changes }));
}

const ConsentRowSchema = z.looseObject({
  kind: z.string(),
  source: z.string(),
  text: z.string().nullish(),
  evidence: z.string().nullish(),
  given_by: z.string(),
  call: z.string().nullish(),
  given_at: z.number(),
});

const ConsentHistorySchema = z.looseObject({
  number: z.string(),
  standing: z.enum(["consented", "opted_out", "unknown"]),
  rows: z.array(ConsentRowSchema),
});

/** What stands for a number, and every fact about it, newest first. */
export type ConsentHistory = z.infer<typeof ConsentHistorySchema>;

/** The two kinds of consent a person records. */
export type ConsentKind = "express" | "written";

const consentDoor = (number: string): string => `/v1/org/consents/${encodeURIComponent(number)}`;

/** `GET /v1/org/consents/{number}`. */
export async function readConsent(credentials: Credentials, number: string): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await read(credentials, consentDoor(number)));
}

/** `POST /v1/org/consents`. */
export async function giveConsent(credentials: Credentials, given: { number: string; kind: ConsentKind; source: string; text: string | null }): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await post(credentials, "/v1/org/consents", given));
}

/** `DELETE /v1/org/consents/{number}`: the number goes onto the do-not-call list. */
export async function optOut(credentials: Credentials, number: string): Promise<ConsentHistory> {
  return ConsentHistorySchema.parse(await drop(credentials, consentDoor(number)));
}

const DoNotCallSchema = z.looseObject({
  numbers: z.array(z.looseObject({ number: z.string(), since: z.number(), source: z.string(), given_by: z.string() })),
  next: z.string().nullish(),
});

/** A page of the do-not-call list. */
export type DoNotCall = z.infer<typeof DoNotCallSchema>;

/** `GET /v1/org/dnc`, the page after the cursor. */
export async function readDoNotCall(credentials: Credentials, after: string | null): Promise<DoNotCall> {
  return DoNotCallSchema.parse(await read(credentials, "/v1/org/dnc", after === null ? {} : { after }));
}

const ImportedSchema = z.looseObject({ added: z.number(), refused: z.array(z.string()) });

/** How many numbers an import added, and the lines that were no number. */
export type Imported = z.infer<typeof ImportedSchema>;

/** `POST /v1/org/dnc`. */
export async function importDoNotCall(credentials: Credentials, numbers: readonly string[], source: string): Promise<Imported> {
  return ImportedSchema.parse(await post(credentials, "/v1/org/dnc", { numbers, source }));
}

const ErasureSchema = z.looseObject({
  id: z.number(),
  at: z.number(),
  what: z.string(),
  subject: z.string(),
  env: z.string().nullish(),
  asked_by: z.string(),
  calls: z.number(),
  entries: z.number(),
  memories: z.number(),
  recordings: z.number(),
});

/** What one erasure took, as the trail says it. */
export type Erasure = z.infer<typeof ErasureSchema>;

/** `GET /v1/org/erasures`, newest first. */
export async function readTrail(credentials: Credentials): Promise<Erasure[]> {
  return z.looseObject({ erasures: z.array(ErasureSchema) }).parse(await read(credentials, "/v1/org/erasures")).erasures;
}

/** `DELETE /v1/contacts/{contact}`: every call they were on in this environment, and every fact kept of them. */
export async function eraseContact(credentials: Credentials, contact: string): Promise<Erasure> {
  return ErasureSchema.parse(await drop(credentials, `/v1/contacts/${encodeURIComponent(contact)}`));
}

/** `DELETE /v1/calls/{call}`: one ended call, its log, facts, memories and recording. */
export async function eraseCall(credentials: Credentials, call: string): Promise<Erasure> {
  return ErasureSchema.parse(await drop(credentials, `/v1/calls/${encodeURIComponent(call)}`));
}

// A download needs the key in a header, which a link cannot carry: the file is fetched and handed to the browser.
/** `GET /v1/org/export`, as a file the browser saves. */
export async function exportWorld(credentials: Credentials): Promise<{ file: Blob; name: string }> {
  const answer = await fetch(doorUrl(credentials, "/v1/org/export"), { headers: headersFor(credentials) });
  if (!answer.ok) throw new GatewayError(answer.status, await answer.text());
  const name = /filename="([^"]+)"/.exec(answer.headers.get("content-disposition") ?? "")?.[1] ?? "pinecall-export.jsonl";
  return { file: await answer.blob(), name };
}

const ReadSchema = z.looseObject({ subject: z.string(), what: z.string(), env: z.string().nullish(), reader: z.string(), at: z.number() });

/** One read of the org's data: the call or number, what of it, who, when. */
export type DataRead = z.infer<typeof ReadSchema>;

/** `GET /v1/org/reads`, newest first; of one call or number when named. */
export async function readReads(credentials: Credentials, subject: string | null): Promise<DataRead[]> {
  return z.looseObject({ reads: z.array(ReadSchema) }).parse(await read(credentials, "/v1/org/reads", subject === null ? {} : { subject })).reads;
}
