/** The Data & privacy and Traceback doors parse the runtime's shapes field for field, knock at its paths, and refuse a renamed field. */

import { expect, test } from "vitest";
import { z } from "zod";

import { readBoxCarriers, readBoxNumbers, readCarrierNetworks, readTraceback } from "../src/screens/box/door-floor";
import { giveConsent, importDoNotCall, optOut, putPolicy, readConsent, readDoNotCall, readPolicy, readReads, readTrail } from "../src/screens/org-data/door";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime wire/rest/accounts.py: OrgPolicyRow, an org that set the hours and its own disclosure.
const A_POLICY = { policy: { retention_days: 365, calling_hours: { from: 9, until: 20 }, per_number_day: null, consent_everywhere: false, disclosure: "Hi, this is Ana.", recording_notice: true }, set_by: "m_ana", set_at: 1758300000 };

// runtime wire/rest/calls.py: Erasure and ReadRow.
const AN_ERASURE = { id: 7, at: 1758300000, what: "contact", subject: "+14155550142", env: "production", asked_by: "m_ana", calls: 3, entries: 212, memories: 4, recordings: 3 };
const A_READ = { subject: "CA_1", what: "recording", env: "production", reader: "m_ana", at: 1758300000 };

// runtime wire/rest/numbers.py: ConsentHistory, DoNotCall, DoNotCallImported.
const A_HISTORY = { number: "+14155550142", standing: "consented", rows: [{ kind: "express", source: "the booking form", text: "Yes, call me", evidence: null, given_by: "m_ana", call: null, given_at: 1758300000 }] };
const A_LIST = { numbers: [{ number: "+14155550142", since: 1758300000, source: "our list", given_by: "m_ana" }], next: "1758300000:+14155550142" };

// runtime wire/rest/ops.py: Traceback, one erased call by its record and one refused dial.
const A_TRACEBACK = {
  number: "+14155550142", since: 1700000000,
  calls: [{ call: "CA_1", org: "org_a", env: "production", direction: "outbound", from_number: "+14155550100", to_number: "+14155550142", started_at: 1758300000, ended_at: 1758300072, end_reason: "agent_hung_up", erased: true }],
  dials: [{ org: "org_a", env: "production", agent: "agenda", call: null, shown: "+14155550100", asked_by: "m_ana", refused: "do_not_call", at: 1758303600 }],
};

// runtime wire/rest/ops.py: BoxNumber, a number another org's older row answers.
const A_BOX_NUMBER = { number: "+14155550142", channel: "phone", org: "otra", env: "production", agent: "agenda", came_in: "hooked", running: false, via: "telnyx", approved: false };

/** Answers every request with the body, and keeps what was asked. */
function answering(body: unknown): { method: string; url: string; body: string | null }[] {
  const asked: { method: string; url: string; body: string | null }[] = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    asked.push({ method: init?.method ?? "GET", url: door.toString(), body: typeof init?.body === "string" ? init.body : null });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
  return asked;
}

test("the policy is read whole and written back whole with one field changed", async () => {
  const asked = answering(A_POLICY);
  expect((await readPolicy(CREDENTIALS)).policy.calling_hours).toEqual({ from: 9, until: 20 });
  await putPolicy(CREDENTIALS, A_POLICY.policy, { recording_notice: false });
  expect(asked.map(({ method, url }) => `${method} ${url}`)).toEqual(["GET https://cloud.pinecall.io/v1/org/policy", "PUT https://cloud.pinecall.io/v1/org/policy"]);
  expect(JSON.parse(asked[1]?.body ?? "{}")).toEqual({ ...A_POLICY.policy, recording_notice: false });
  answering({ ...A_POLICY, policy: { ...A_POLICY.policy, calling_hours: { from: 9, till: 20 } } });
  await expect(readPolicy(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("the trail and the reads are the runtime's rows, and one call's reads are asked by its id", async () => {
  answering({ erasures: [AN_ERASURE] });
  expect((await readTrail(CREDENTIALS))[0]?.recordings).toBe(3);
  const asked = answering({ reads: [A_READ] });
  expect((await readReads(CREDENTIALS, "CA_1"))[0]?.reader).toBe("m_ana");
  expect(asked[0]?.url).toBe("https://cloud.pinecall.io/v1/org/reads?subject=CA_1");
  answering({ reads: [{ ...A_READ, what: "state" }] });
  await expect(readReads(CREDENTIALS, null)).rejects.toBeInstanceOf(z.ZodError);
});

test("a number's consent is read, given and taken away at the consent doors, and the list at the dnc doors", async () => {
  const asked = answering(A_HISTORY);
  expect((await readConsent(CREDENTIALS, "+14155550142")).standing).toBe("consented");
  await giveConsent(CREDENTIALS, { number: "+14155550142", kind: "written", source: "a signed form", text: null });
  await optOut(CREDENTIALS, "+14155550142");
  expect(asked.map(({ method, url }) => `${method} ${url}`)).toEqual([
    "GET https://cloud.pinecall.io/v1/org/consents/%2B14155550142",
    "POST https://cloud.pinecall.io/v1/org/consents",
    "DELETE https://cloud.pinecall.io/v1/org/consents/%2B14155550142",
  ]);
  const listed = answering(A_LIST);
  expect((await readDoNotCall(CREDENTIALS, A_LIST.next)).numbers[0]?.source).toBe("our list");
  expect(listed[0]?.url).toBe("https://cloud.pinecall.io/v1/org/dnc?after=1758300000%3A%2B14155550142");
  const imported = answering({ added: 2, refused: ["x"] });
  expect((await importDoNotCall(CREDENTIALS, ["+14155550142", "+14155550143", "x"], "scrub")).refused).toEqual(["x"]);
  expect(JSON.parse(imported[0]?.body ?? "{}")).toEqual({ numbers: ["+14155550142", "+14155550143", "x"], source: "scrub" });
  answering({ ...A_HISTORY, standing: "maybe" });
  await expect(readConsent(CREDENTIALS, "+14155550142")).rejects.toBeInstanceOf(z.ZodError);
});

test("a traceback is asked by number and day and read as the runtime's calls and dials", async () => {
  const asked = answering(A_TRACEBACK);
  const found = await readTraceback(CREDENTIALS, "+14155550142", 1700000000);
  expect(found.calls[0]?.erased).toBe(true);
  expect(found.dials[0]?.refused).toBe("do_not_call");
  expect(asked[0]?.url).toBe("https://cloud.pinecall.io/v1/ops/traceback?number=%2B14155550142&since=1700000000");
  answering({ ...A_TRACEBACK, calls: [{ ...A_TRACEBACK.calls[0], erased: "yes" }] });
  await expect(readTraceback(CREDENTIALS, "+14155550142", null)).rejects.toBeInstanceOf(z.ZodError);
});

test("the box's numbers are read whole at one door, and a row without whether it is approved is refused", async () => {
  const asked = answering([A_BOX_NUMBER]);
  expect(await readBoxNumbers(CREDENTIALS)).toEqual([A_BOX_NUMBER]);
  expect(asked[0]?.url).toBe("https://cloud.pinecall.io/v1/ops/numbers");
  answering([{ ...A_BOX_NUMBER, approved: undefined }]);
  await expect(readBoxNumbers(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

// runtime wire/rest/ops.py: BoxCarriers and CarrierNetworkRow.
const A_BOX_CARRIERS = {
  carriers: [{ kind: "telnyx", name: "Telnyx", control: false, networks: ["192.76.120.10/32"], source: "https://sip.telnyx.com/", read_on: "2026-10-03", admitted: true, fixed: false, numbers: 1 }],
  fence: { openings: [{ network: "192.76.120.10/32", reason: "telnyx" }], networks: ["54.172.60.0/30", "192.76.120.10/32"] },
};
const AN_ASK = { id: 7, org: "clinica", source: "pbx", network: "45.60.12.7/32", state: "waiting", asked_at: 1758300000, decided_by: null, decided_at: null };

test("the box's carriers and the addresses orgs asked for are read at their doors, a state renamed refused", async () => {
  const asked = answering(A_BOX_CARRIERS);
  expect((await readBoxCarriers(CREDENTIALS)).fence.openings[0]?.reason).toBe("telnyx");
  expect(asked[0]?.url).toBe("https://cloud.pinecall.io/v1/ops/carriers");
  answering([AN_ASK]);
  expect((await readCarrierNetworks(CREDENTIALS))[0]?.network).toBe("45.60.12.7/32");
  answering([{ ...AN_ASK, state: "pending" }]);
  await expect(readCarrierNetworks(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});
