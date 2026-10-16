/** The Alerts screen reads the webhook as the runtime says it, sets it with the secret in the body, drops it, and reads a test's answer. */

import { expect, test } from "vitest";
import { z } from "zod";

import { dropWebhook, putWebhook, readWebhook, testWebhook } from "../src/screens/alerts/door";

const CREDENTIALS = { base: "/", key: "pk_test" };
// runtime wire/rest/webhooks.py: WebhookResponse.
const A_WEBHOOK = { url: "https://hooks.example.test/alerts", signed: true };

let asked: { url: string; method: string; body: unknown }[] = [];

function answering(body: unknown): void {
  asked = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ url: url.toString(), method: init?.method ?? "GET", body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("the webhook is read as its URL and whether posts are signed, null when alerts go nowhere, and a renamed field is refused", async () => {
  answering(A_WEBHOOK);
  expect(await readWebhook(CREDENTIALS)).toEqual(A_WEBHOOK);
  answering(null);
  expect(await readWebhook(CREDENTIALS)).toBeNull();
  answering({ url: A_WEBHOOK.url, signs: true });
  await expect(readWebhook(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("setting it sends the URL and the secret once, a test is a POST read as sent or why not, dropping is a DELETE", async () => {
  answering(null);
  await putWebhook(CREDENTIALS, A_WEBHOOK.url, "shh");
  expect(asked[0]).toEqual({ url: "https://cloud.pinecall.io/v1/webhook", method: "PUT", body: { url: A_WEBHOOK.url, secret: "shh" } });
  answering({ sent: false, error: "HTTP 404" });
  expect(await testWebhook(CREDENTIALS)).toEqual({ sent: false, error: "HTTP 404" });
  expect(asked[0]).toMatchObject({ url: "https://cloud.pinecall.io/v1/webhook/test", method: "POST" });
  answering(null);
  await dropWebhook(CREDENTIALS);
  expect(asked[0]?.method).toBe("DELETE");
});
