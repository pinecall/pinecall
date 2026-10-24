/** Telephony against the gateway: numbers imported and bought, carrier accounts with their secrets, the line, the caller's own phone. */

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { UsageError } from "../../src/errors.js";
import * as service from "../../src/telephony/service.js";
import { answer, GATEWAY } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { LIMITS } from "../support/fixtures.js";
import { folder, project } from "../support/project.js";

const A_ROUTE = { org: "org_1", agent: "front-desk", channel: "phone", number: "+34910000000", env: "sandbox", managed: false };
const A_PLAN = { route: A_ROUTE, steps: ["point +34910000000's voice URL at the SFU trunk", "route it to front-desk"], dry_run: true };
const A_LINE = { agent: "front-desk", env: "sandbox", held: true, holding: { holder: "mem_ana", name: "ana@clinica.test" }, yours: false, waiting: [], calling: [] };

describe("numbers", () => {
  it("imports with only the fields named, as a dry run in the query", async () => {
    const sent = answer("post", "/v1/numbers", A_PLAN);
    const { ctx } = testContext();
    const plan = await service.importNumber(ctx, service.ImportNumberInput.parse({ number: "+34910000000", agent: "front-desk", dryRun: true }));
    expect(plan).toEqual(A_PLAN);
    expect(sent[0]!.body).toEqual({ number: "+34910000000", agent: "front-desk" });
    expect(sent[0]!.query).toEqual({ dry_run: "true" });
  });

  // T F10: `--dry-run --move` still answered "so say move": the flag never reached the body.
  it("says move when asked, the dry run included", async () => {
    const sent = answer("post", "/v1/numbers", A_PLAN);
    const { ctx } = testContext();
    await service.importNumber(ctx, service.ImportNumberInput.parse({ number: "+34910000000", agent: "front-desk", move: true, dryRun: true }));
    expect(sent[0]!.body).toEqual({ number: "+34910000000", agent: "front-desk", move: true });
  });

  it("imports for real with no query at all", async () => {
    const sent = answer("post", "/v1/numbers", { ...A_PLAN, dry_run: false });
    const { ctx } = testContext();
    await service.importNumber(ctx, service.ImportNumberInput.parse({ number: "+34910000000", agent: "front-desk", account: "AC9", channel: "whatsapp" }));
    expect(sent[0]!.query).toEqual({});
    expect(sent[0]!.body).toEqual({ number: "+34910000000", agent: "front-desk", account: "AC9", channel: "whatsapp" });
  });

  it("refuses a number that is not +E.164 before anything is sent", () => {
    expect(() => service.ImportNumberInput.parse({ number: "910000000", agent: "front-desk" })).toThrow(/\+E\.164/);
  });

  it("buys with the country upper-cased and answers the stock of bought numbers", async () => {
    const sent = answer("post", "/v1/numbers/buy", A_PLAN);
    answer("get", "/v1/limits", { ...LIMITS, numbers: { limit: 2, used: 1 } });
    answer("get", "/v1/provider-keys", { vendors: [] });
    const { ctx } = testContext();
    const bought = await service.buyNumber(ctx, service.BuyNumberInput.parse({ country: "es", agent: "front-desk", areaCode: "91", dryRun: true }));
    expect(sent[0]!.body).toEqual({ country: "ES", agent: "front-desk", area_code: "91" });
    expect(bought.stock).toEqual({ limit: 2, used: 1 });
  });

  it("drops a number by its path, escaped", async () => {
    const sent = answer("delete", "/v1/numbers/:number");
    const { ctx } = testContext();
    await service.dropNumber(ctx, "+34910000000");
    expect(sent[0]!.path).toBe("/v1/numbers/%2B34910000000");
  });
});

describe("carriers", () => {
  it("counts the numbers each account routes in this env", async () => {
    answer("get", "/v1/carriers", { carriers: [{ kind: "twilio", account: "AC1", label: "", networks: [] }, { kind: "sip", account: "pbx", label: "", networks: [] }] });
    answer("get", "/v1/numbers", [
      { route: A_ROUTE, origin: "imported", rings: "ok", last_call_at: null, via: null, account: "AC1" },
      { route: A_ROUTE, origin: "imported", rings: "ok", last_call_at: null, via: null, account: "AC1" },
    ]);
    const { ctx } = testContext();
    expect((await service.listCarriers(ctx)).map((one) => [one.account, one.routed])).toEqual([["AC1", 2], ["pbx", 0]]);
  });

  it("asks for no numbers when the org holds no account", async () => {
    answer("get", "/v1/carriers", { carriers: [] });
    const { ctx } = testContext();
    expect(await service.listCarriers(ctx)).toEqual([]);
  });

  it("a SIP peer takes its password, and the outbound one only with an outbound user", () => {
    const plain = service.AddCarrierInput.parse({ kind: "sip", username: "pbx", addresses: ["203.0.113.0/24"] });
    expect(service.secretsOf(plain).map(([, field]) => field)).toEqual(["password"]);
    const outbound = service.AddCarrierInput.parse({ kind: "sip", username: "pbx", addresses: ["203.0.113.7"], outboundUsername: "out" });
    expect(service.secretsOf(outbound).map(([, field]) => field)).toEqual(["password", "outbound_password"]);
  });

  it("keeps a SIP peer with its secrets trimmed, the outbound fields only when named", async () => {
    const sent = answer("put", "/v1/carrier", { kind: "sip", account: "pbx", label: "Sede", networks: [{ network: "203.0.113.7/32", state: "waiting" }] });
    const { ctx } = testContext();
    const input = service.AddCarrierInput.parse({ kind: "sip", username: "pbx", addresses: ["203.0.113.7"], outboundHost: "sip.example.com", outboundUsername: "out", label: "Sede" });
    await service.addCarrier(ctx, input, { password: " p1 ", outbound_password: "p2\n" });
    expect(sent[0]!.body).toEqual({
      kind: "sip",
      username: "pbx",
      password: "p1",
      addresses: ["203.0.113.7"],
      outbound_host: "sip.example.com",
      outbound_username: "out",
      outbound_password: "p2",
      label: "Sede",
    });
  });

  it("keeps nothing when a secret is missing", async () => {
    const { ctx } = testContext();
    const input = service.AddCarrierInput.parse({ kind: "twilio", accountSid: "AC1", user: "SK1" });
    await expect(service.addCarrier(ctx, input, { secret: "  " })).rejects.toBeInstanceOf(UsageError);
  });

  it("names the account in the query, or none for the org's only one", async () => {
    const sent = answer("delete", "/v1/carrier");
    const { ctx } = testContext();
    await service.dropCarrier(ctx, "AC1");
    await service.dropCarrier(ctx);
    expect(sent.map((one) => one.query)).toEqual([{ account: "AC1" }, {}]);
  });
});

describe("the line", () => {
  it("asks for the project's one agent", async () => {
    const sent = answer("get", "/v1/agents/:slug/line", A_LINE);
    const { ctx } = testContext();
    expect(await service.showLine(ctx, {})).toEqual(A_LINE);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/line");
  });

  it("takes --agent as the gateway's slug from a folder that holds no project", async () => {
    const sent = answer("post", "/v1/agents/:slug/line", { ...A_LINE, agent: "sales", yours: true });
    const { ctx } = testContext({ cwd: folder() });
    await service.claimLine(ctx, { agent: "sales" });
    expect(sent[0]!.path).toBe("/v1/agents/sales/line");
  });

  it("asks a project of several agents which one", async () => {
    const { ctx } = testContext({ cwd: project(["front-desk", "sales"]) });
    await expect(service.releaseLine(ctx, {})).rejects.toThrow(/--agent front-desk or --agent sales/);
  });
});

describe("the caller's own phone", () => {
  it("refuses a number that is not +E.164", async () => {
    const { ctx } = testContext();
    await expect(service.setCallerNumber(ctx, "600 000 000")).rejects.toBeInstanceOf(UsageError);
  });

  it("says it to the gateway and keeps it on this machine for a gateway it is signed in to", async () => {
    const home = folder();
    writeFileSync(join(home, "session.json"), JSON.stringify({ gateways: { [GATEWAY]: { key: "pc_live_machine" } }, last: GATEWAY }));
    const sent = answer("put", "/v1/line/from", { calling: ["+34600000000"] });
    const { ctx } = testContext({ home });
    expect(await service.setCallerNumber(ctx, "+34600000000")).toEqual({ calling: ["+34600000000"] });
    expect(sent[0]!.body).toEqual({ number: "+34600000000" });
    expect(JSON.parse(readFileSync(join(home, "session.json"), "utf8")).gateways[GATEWAY].calling).toBe("+34600000000");
  });

  it("is said again by start, and only when one was kept", async () => {
    const home = folder();
    writeFileSync(join(home, "session.json"), JSON.stringify({ gateways: { [GATEWAY]: { key: "k", calling: "+34600000000" } }, last: GATEWAY }));
    const sent = answer("put", "/v1/line/from", { calling: ["+34600000000"] });
    await service.resendCallerNumber(testContext({ home }).ctx);
    await service.resendCallerNumber(testContext().ctx);
    expect(sent.map((one) => one.body)).toEqual([{ number: "+34600000000" }]);
  });
});

describe("callbacks", () => {
  it("asks one agent's from a cursor", async () => {
    const sent = answer("get", "/v1/callbacks", { requests: [], next: null });
    const { ctx } = testContext();
    await service.listCallbacks(ctx, { agent: "front-desk", after: 40 });
    expect(sent[0]!.query).toEqual({ agent: "front-desk", after: "40" });
  });
});
