/** The Apps and Secrets screens parse the gateway's hosting shapes field for field and refuse a renamed one. */

import { expect, test } from "vitest";
import { z } from "zod";

import { readHosted, readLogs, readReleases, readServed, rollBack } from "../src/screens/apps/door";
import { putSecret, readSecrets } from "../src/screens/secrets/door";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime wire/rest/hosting.py, as the doors answer it.
const AN_APP = { name: "clinica-norte", release: 3, live_release: 2, failed_why: null, stopped: false, created_by: "ana@clinica.uy", created_at: 1.5 };
const A_RELEASE = { name: "clinica-norte", release: 3, sha256: "ab".repeat(32), bytes: 20480, author: "ana@clinica.uy", note: "", created_at: 2.5 };
const A_SECRET = { name: "CRM_TOKEN", set_by: "ana@clinica.uy", set_at: 3.5 };

let asked: { url: string; method: string; body: unknown }[] = [];

function answering(body: unknown): void {
  asked = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ url: url.toString(), method: init?.method ?? "GET", body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("an app is its newest release, the one serving, why it failed and whether it was stopped", async () => {
  answering({ apps: [AN_APP] });
  expect((await readHosted(CREDENTIALS))[0]?.live_release).toBe(2);
  answering({ apps: [{ ...AN_APP, stopped: undefined }] });
  await expect(readHosted(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("a rollback names the release whose sources go again, and answers the new release", async () => {
  answering({ releases: [A_RELEASE] });
  expect((await readReleases(CREDENTIALS, "clinica-norte"))[0]?.bytes).toBe(20480);
  answering({ ...A_RELEASE, release: 4 });
  expect((await rollBack(CREDENTIALS, "clinica-norte", 2)).release).toBe(4);
  expect(asked[0]).toEqual({ url: "https://cloud.pinecall.io/v1/hosted/clinica-norte/rollback", method: "POST", body: { release: 2 } });
});

test("logs are null-timed until the runner has sent any, and served time is per app per day", async () => {
  answering({ name: "clinica-norte", host: null, lines: "", at: null });
  expect((await readLogs(CREDENTIALS, "clinica-norte")).at).toBeNull();
  answering({ since: "2026-09-01", until: "2026-10-01", rows: [{ org: "clinica", env: "production", name: "clinica-norte", day: "2026-09-02", seconds: 60 }] });
  expect((await readServed(CREDENTIALS))[0]?.seconds).toBe(60);
  expect(asked[0]?.url).toBe("https://cloud.pinecall.io/v1/hosted/usage");
});

test("a secret is listed without a value, and one is set by its name with the value in the body", async () => {
  answering({ secrets: [A_SECRET] });
  expect(await readSecrets(CREDENTIALS)).toEqual([A_SECRET]);
  answering({ secrets: [A_SECRET] });
  await putSecret(CREDENTIALS, "CRM_TOKEN", "s3cret");
  expect(asked[0]).toEqual({ url: "https://cloud.pinecall.io/v1/secrets/CRM_TOKEN", method: "PUT", body: { value: "s3cret" } });
});
