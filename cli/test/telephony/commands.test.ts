/** `pinecall numbers | carriers | line | callbacks` as typed: the plans printed, secrets off stdin, the line in words. */

import { describe, expect, it } from "vitest";

import { answer, refuse } from "../support/gateway.js";
import { LIMITS } from "../support/fixtures.js";
import { folder } from "../support/project.js";
import { run, runJson } from "../support/run.js";

const A_ROUTE = { org: "org_1", agent: "front-desk", channel: "phone", number: "+34910000000", env: "sandbox", managed: false };
const A_ROW = { route: A_ROUTE, origin: "imported", rings: "ok", last_call_at: null, via: null, account: "AC0123" };
const STEPS = ["point +34910000000's voice URL at the SFU trunk", "route it to front-desk"];
const HELD_ELSEWHERE = { agent: "front-desk", env: "sandbox", held: true, holding: { holder: "mem_ana", name: "ana@clinica.test" }, yours: false, waiting: [], calling: [] };

describe("pinecall numbers", () => {
  it("alone lists this env's numbers", async () => {
    answer("get", "/v1/numbers", [A_ROW, { ...A_ROW, route: { ...A_ROUTE, number: "+34910000001", managed: true }, account: null }]);
    const ran = await run(["numbers"]);
    expect(ran.out).toBe("+34910000000 · phone · → front-desk · sandbox · AC0123\n+34910000001 · phone · → front-desk · sandbox · bought here\n");
  });

  it("import --dry-run prints the steps and says nothing was written", async () => {
    const sent = answer("post", "/v1/numbers", { route: A_ROUTE, steps: STEPS, dry_run: true });
    const ran = await run(["numbers", "import", "+34910000000", "--agent", "front-desk", "--dry-run"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.query).toEqual({ dry_run: "true" });
    expect(ran.out).toBe(`  ${STEPS[0]}\n  ${STEPS[1]}\n  nothing written: drop --dry-run to do it\n`);
  });

  it("import names the --account flag when the gateway says the org holds several", async () => {
    refuse("post", "/v1/numbers", 409, "the org holds 2 accounts: name one of them");
    const ran = await run(["numbers", "import", "+34910000000", "--agent", "front-desk"]);
    expect(ran.code).toBe(1);
    expect(ran.err).toContain("--account <id>");
  });

  it("import needs --agent", async () => {
    expect((await run(["numbers", "import", "+34910000000"])).code).toBe(2);
  });

  it("buy prints how many bought numbers the env holds", async () => {
    answer("post", "/v1/numbers/buy", { route: { ...A_ROUTE, managed: true }, steps: ["buy +34910000000"], dry_run: true });
    answer("get", "/v1/limits", { ...LIMITS, numbers: { limit: 2, used: 1 } });
    answer("get", "/v1/provider-keys", { vendors: [] });
    const ran = await run(["numbers", "buy", "--country", "es", "--agent", "front-desk", "--dry-run"]);
    expect(ran.out).toContain("bought numbers in this env: 1 of 2");
    expect(ran.out).toContain("nothing bought: drop --dry-run to buy +34910000000");
  });
});

describe("pinecall carriers", () => {
  it("add twilio reads its secret off stdin", async () => {
    const sent = answer("put", "/v1/carrier", { kind: "twilio", account: "AC0123", label: "Clínica", networks: [] });
    const ran = await run(["carriers", "add", "twilio", "--account-sid", "AC0123", "--user", "SK4567", "--label", "Clínica"], { stdin: "tw-secret\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ kind: "twilio", account_sid: "AC0123", user: "SK4567", secret: "tw-secret", label: "Clínica" });
    expect(ran.out).toContain("kept: AC0123 · twilio · Clínica");
    expect(ran.out).not.toContain("tw-secret");
  });

  it("add sip reads the password, then the outbound one, one line each", async () => {
    const sent = answer("put", "/v1/carrier", { kind: "sip", account: "pbx", label: "", networks: [{ network: "203.0.113.7/32", state: "waiting" }] });
    const ran = await run(["carriers", "add", "sip", "--username", "pbx", "--address", "203.0.113.7", "--outbound-username", "out"], { stdin: "p1\np2\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toMatchObject({ password: "p1", outbound_username: "out", outbound_password: "p2" });
    expect(ran.out).toContain("each waiting network opens once Pinecall's operator approves it");
  });

  it("add with no secret piped keeps nothing", async () => {
    const ran = await run(["carriers", "add", "whatsapp", "--phone-number-id", "1099"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("no WhatsApp access token was given");
  });

  it("alone lists the accounts and how many numbers each routes", async () => {
    answer("get", "/v1/carriers", { carriers: [{ kind: "twilio", account: "AC0123", label: "", networks: [] }] });
    answer("get", "/v1/numbers", [A_ROW]);
    expect((await run(["carriers"])).out).toBe("AC0123 · twilio · 1 number here\n");
  });
});

describe("pinecall line", () => {
  it("alone says whose terminal a ring lands in", async () => {
    answer("get", "/v1/agents/:slug/line", HELD_ELSEWHERE);
    expect((await run(["line"])).out).toContain("rings in ana@clinica.test · `pinecall line from <+your-number>` routes yours");
  });

  it("--agent reads the gateway's slug from any folder", async () => {
    const sent = answer("get", "/v1/agents/:slug/line", { ...HELD_ELSEWHERE, agent: "sales", held: false, holding: null });
    const ran = await run(["line", "--agent", "sales"], { cwd: folder() });
    expect(ran.code).toBe(0);
    expect(sent[0]!.path).toBe("/v1/agents/sales/line");
    expect(ran.out).toContain("nobody is answering sales");
  });

  it("from refuses a number that is not +E.164", async () => {
    const ran = await run(["line", "from", "600000000"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("+E.164");
  });

  it("release says when nobody else picks the line up", async () => {
    answer("delete", "/v1/agents/:slug/line", { ...HELD_ELSEWHERE, held: false, holding: null });
    expect((await run(["line", "release"])).out).toContain("let go, and nobody else is running front-desk");
  });
});

describe("pinecall callbacks", () => {
  it("says where it connected on stderr and the page on stdout, with the cursor to read on", async () => {
    answer("get", "/v1/callbacks", {
      requests: [{ position: 1, agent: "front-desk", ts: 1_792_150_000, channel: "phone", number: "+34600000001", via: "overflow", call: "call_1" }],
      next: 7,
    });
    const ran = await run(["callbacks"]);
    expect(ran.err).toContain("gateway https://gateway.test · key from the environment · sandbox");
    expect(ran.out).toContain("front-desk  +34600000001  phone  via overflow on call_1");
    expect(ran.out).toContain("more: --after 7");
  });

  it("refuses a cursor that is not one", async () => {
    expect((await run(["callbacks", "--after", "x"])).code).toBe(2);
  });

  it("--json is the page", async () => {
    answer("get", "/v1/callbacks", { requests: [], next: null });
    expect(await runJson(["callbacks"])).toEqual({ requests: [], next: null });
  });
});
