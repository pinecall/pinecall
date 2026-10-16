// The tenant's server holds the key: it mints a seat's ticket, places a call, asks for a code, and a refusal keeps the gateway's sentence.

import { describe, expect, it } from "vitest";

// `expect` is vitest's here: the server's is named for what it asks.
import { dial, expect as askForACode, GatewayRefused, mint } from "../src/server/index.js";

const KEY = "pk_test_not_a_real_key";

interface Posted {
  url: string;
  method: string | undefined;
  authorization: string | null;
  body: unknown;
  timed: boolean;
}

/** A gateway that answers every request with `status` and `body`, and writes each one down. */
function gateway(status: number, body: string): { fetch: typeof fetch; posted: Posted[] } {
  const posted: Posted[] = [];
  return {
    posted,
    fetch: async (input, init) => {
      posted.push({
        url: String(input),
        method: init?.method,
        authorization: new Headers(init?.headers).get("authorization"),
        body: typeof init?.body === "string" ? JSON.parse(init.body) : null,
        timed: init?.signal instanceof AbortSignal,
      });
      return new Response(body, { status });
    },
  };
}

const MINTED = { server_url: "wss://lk.example", participant_token: "ticket", call: "call_1", log_token: "log_1" };
const CODE = { code: "4821", number: "+34910000000", expires_at: 1_790_000_600, code_token: "code_1" };
const DIALED = { call: "call_2", agent: "clinica", to: "+34600000001", from: "+34910000000", env: "production", log_token: "log_2" };

describe("the server", () => {
  it("mints with the key: {agent, scope, ttl_s} to /v1/tokens, the bearer on the header", async () => {
    const { fetch, posted } = gateway(200, JSON.stringify(MINTED));
    const minted = await mint(KEY, { url: "https://gw.example/", agent: "clinica", scope: "talk", ttl_s: 120, fetch });

    expect(minted).toEqual(MINTED);
    expect(posted).toEqual([
      {
        url: "https://gw.example/v1/tokens",
        method: "POST",
        authorization: `Bearer ${KEY}`,
        body: { agent: "clinica", scope: "talk", ttl_s: 120 },
        timed: true,
      },
    ]);
  });

  it("sends the resume token a page kept as `resume`, and the agent may be left to the call", async () => {
    const { fetch, posted } = gateway(200, JSON.stringify({ ...MINTED, resume_token: "resume_2" }));
    const minted = await mint(KEY, { url: "https://gw.example", agent: "", scope: "chat", resume: "resume_1", fetch });

    expect(minted.resume_token).toBe("resume_2");
    expect(posted[0]?.body).toEqual({ scope: "chat", resume: "resume_1" });
  });

  it("asks for the projection the page reads the call through, when told: `log` on the body", async () => {
    const { fetch, posted } = gateway(200, JSON.stringify(MINTED));
    const minted = await mint(KEY, { url: "https://gw.example", agent: "clinica", scope: "chat", log: "tenant", fetch });
    expect(minted.log_token).toBe("log_1");
    expect(posted[0]?.body).toEqual({ agent: "clinica", scope: "chat", log: "tenant" });
  });

  it("dials with the key: {to, from} to /v1/agents/{agent}/dial", async () => {
    const { fetch, posted } = gateway(202, JSON.stringify(DIALED));
    const dialed = await dial(KEY, { url: "https://gw.example", agent: "clinica", to: "+34600000001", fetch });

    expect(dialed).toEqual(DIALED);
    expect(posted[0]?.url).toBe("https://gw.example/v1/agents/clinica/dial");
    expect(posted[0]?.body).toEqual({ to: "+34600000001" });
    expect(posted[0]?.authorization).toBe(`Bearer ${KEY}`);
  });

  it("asks for a code with the key: {agent, ttl_s, log} to /v1/codes", async () => {
    const { fetch, posted } = gateway(201, JSON.stringify(CODE));
    const code = await askForACode(KEY, { url: "https://gw.example/", agent: "clinica", ttl_s: 300, log: "tenant", fetch });

    expect(code).toEqual(CODE);
    expect(posted).toEqual([
      {
        url: "https://gw.example/v1/codes",
        method: "POST",
        authorization: `Bearer ${KEY}`,
        body: { agent: "clinica", ttl_s: 300, log: "tenant" },
        timed: true,
      },
    ]);
  });

  it("refuses a code the gateway answered in a shape it does not know", async () => {
    const { fetch } = gateway(201, JSON.stringify({ ...CODE, expires_at: "soon" }));
    const asked = askForACode(KEY, { url: "https://gw.example", agent: "clinica", fetch });

    await expect(asked).rejects.toThrow("the gateway answered /v1/codes with a shape this package does not know");
  });

  it("keeps the gateway's sentence when the agent answers at no number", async () => {
    const detail = "agent clinica answers at no phone number in production: pinecall numbers import";
    const { fetch } = gateway(409, JSON.stringify({ detail }));
    const asked = askForACode(KEY, { url: "https://gw.example", agent: "clinica", fetch });

    await expect(asked).rejects.toMatchObject({ status: 409, detail });
  });

  it("throws GatewayRefused with the gateway's own sentence", async () => {
    const { fetch } = gateway(429, JSON.stringify({ detail: "more dials this minute than the org's per_minute" }));
    const refused = dial(KEY, { url: "https://gw.example", agent: "clinica", to: "+34600000001", fetch });

    await expect(refused).rejects.toBeInstanceOf(GatewayRefused);
    await expect(refused).rejects.toMatchObject({
      status: 429,
      detail: "more dials this minute than the org's per_minute",
      message: "more dials this minute than the org's per_minute",
    });
  });

  it("throws the status alone when the body is not the gateway's JSON", async () => {
    const { fetch } = gateway(502, "<html>bad gateway</html>");
    const refused = mint(KEY, { url: "https://gw.example", agent: "clinica", scope: "chat", fetch });

    await expect(refused).rejects.toMatchObject({ status: 502, detail: null, message: "the gateway answered 502" });
  });
});
