/** The org's data against the gateway: the policy one field at a time, consent and its rules, the do-not-call list, the export. */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Writable } from "node:stream";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import * as service from "../../../src/calls/service/data.js";
import { UsageError } from "../../../src/errors.js";
import { answer, GATEWAY, server } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder, write } from "../../support/project.js";

const ROW = { policy: { retention_days: 90, calling_hours: { from: 9, until: 20 }, per_number_day: 3, consent_everywhere: false, disclosure: null, recording_notice: true }, set_by: "m_ana", set_at: 1_792_000_000 };

describe("the policy", () => {
  it("with no flag is read, and nothing is written", async () => {
    answer("get", "/v1/org/policy", ROW);
    const { ctx } = testContext();
    expect(await service.policy(ctx, service.PolicyInput.parse({}))).toEqual(ROW);
  });

  it("a flag changes its field and the row travels whole", async () => {
    answer("get", "/v1/org/policy", ROW);
    const sent = answer("put", "/v1/org/policy", ROW);
    const { ctx } = testContext();
    await service.policy(ctx, service.PolicyInput.parse({ keepAll: true, callingHours: "8-21", noDisclosure: true, consentEverywhere: true }));
    expect(sent[0]!.body).toEqual({ ...ROW.policy, retention_days: null, calling_hours: { from: 8, until: 21 }, disclosure: "", consent_everywhere: true });
  });

  it("refuses two things said about one field, and hours that are no window of a day", async () => {
    const { ctx } = testContext();
    await expect(service.policy(ctx, service.PolicyInput.parse({ retentionDays: 30, keepAll: true }))).rejects.toThrow("--retention-days and --keep-all say two things about one field");
    await expect(service.policy(ctx, service.PolicyInput.parse({ disclosure: "Hi", platformDisclosure: true }))).rejects.toThrow(/one of --disclosure/);
    expect(service.hoursOf("21-8")).toBeUndefined();
    expect(service.hoursOf("0-24")).toEqual({ from: 0, until: 24 });
    expect(() => service.PolicyInput.parse({ callingHours: "9am-8pm" })).toThrow(/like 9-20/);
  });
});

describe("consent", () => {
  it("given needs where it came from; read with no flag; an opt-out puts the number on the list", async () => {
    const given = answer("post", "/v1/org/consents", { number: "+15550001", standing: "consented", rows: [] });
    const read = answer("get", "/v1/org/consents/:number", { number: "+15550001", standing: "unknown", rows: [] });
    const opted = answer("delete", "/v1/org/consents/:number", { number: "+15550001", standing: "opted_out", rows: [] });
    const { ctx } = testContext();
    await expect(service.consent(ctx, service.ConsentInput.parse({ number: "+15550001", give: "written" }))).rejects.toThrow(/--give needs --source/);
    await service.consent(ctx, service.ConsentInput.parse({ number: "+15550001", give: "written", source: " signed form " }));
    await service.consent(ctx, service.ConsentInput.parse({ number: "+15550001" }));
    await service.consent(ctx, service.ConsentInput.parse({ number: "+15550001", optOut: true }));
    expect(given[0]!.body).toEqual({ number: "+15550001", kind: "written", source: "signed form", text: null, evidence: null });
    expect([read.length, opted.length]).toEqual([1, 1]);
  });

  it("refuses a consent and an opt-out at once, and evidence with no consent", async () => {
    const { ctx } = testContext();
    await expect(service.consent(ctx, service.ConsentInput.parse({ number: "+1", give: "express", optOut: true }))).rejects.toBeInstanceOf(UsageError);
    await expect(service.consent(ctx, service.ConsentInput.parse({ number: "+1", evidence: "a photo" }))).rejects.toThrow(/go with --give/);
  });
});

describe("the do-not-call list", () => {
  it("an import reads one number a line, blanks dropped, before the gateway is asked", async () => {
    const sent = answer("post", "/v1/org/dnc", { added: 2, refused: [] });
    const file = write(folder(), "dnc.txt", "+15550001\r\n\n  +15550002  \n");
    const { ctx } = testContext();
    await service.importDoNotCall(ctx, file, " complaint ");
    expect(sent[0]!.body).toEqual({ numbers: ["+15550001", "+15550002"], source: "complaint" });
    await expect(service.importDoNotCall(ctx, write(folder(), "empty.txt", "\n"), "x")).rejects.toThrow(/one number a line/);
  });
});

describe("the export", () => {
  const LINES = '{"type":"call"}\n{"type":"entry"}\n';

  it("is written to a file, or streamed into one the caller holds", async () => {
    server.use(http.get(`${GATEWAY}/v1/org/export`, () => new HttpResponse(LINES, { headers: { "content-type": "application/x-ndjson" } })));
    const { ctx } = testContext();
    const file = join(folder(), "org.jsonl");
    expect(await service.exportOrg(ctx, file)).toEqual({ file });
    expect(readFileSync(file, "utf8")).toBe(LINES);
    let streamed = "";
    const into = new Writable({ write: (chunk, _encoding, done) => ((streamed += String(chunk)), done()) });
    expect(await service.exportOrg(ctx, into)).toEqual({ file: null });
    expect(streamed).toBe(LINES);
  });
});
