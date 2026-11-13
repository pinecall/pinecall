// A page deployed with its app asks its own name for its ticket, its code and its dictation, and says the server's own sentence when refused.

import { describe, expect, it } from "vitest";

import { hosted } from "../src/index.js";

const MINTED = { server_url: "wss://lk.example", participant_token: "pt", call: "call_1", log_token: "lt", resume_token: "rt" };
const CODE = { code: "4821", number: "+14155550134", expires_at: 1_800_000_000, code_token: "ct" };

/** A page's server with no captcha: what it was asked, and what it answers each path. */
function server(answers: Record<string, { status: number; body: unknown }>): { fetch: typeof fetch; asked: { path: string; body: unknown }[] } {
  const asked: { path: string; body: unknown }[] = [];
  const answer: typeof fetch = async (input, init) => {
    const path = String(input);
    if (path.endsWith("/pinecall/config")) return Response.json({ agent: "front-desk", turnstile: null });
    asked.push({ path, body: JSON.parse(String(init?.body ?? "{}")) });
    const said = answers[path] ?? { status: 404, body: { detail: "no such route" } };
    return Response.json(said.body, { status: said.status });
  };
  return { fetch: answer, asked };
}

describe("hosted()", () => {
  it("asks the page's own name for a ticket, with the scope and the conversation to resume", async () => {
    const page = server({ "/pinecall/token": { status: 201, body: MINTED } });
    const { tokens } = hosted({ fetch: page.fetch });

    expect(await tokens("chat")).toEqual(MINTED);
    await tokens("talk", "kept");
    expect(page.asked).toEqual([
      { path: "/pinecall/token", body: { scope: "chat" } },
      { path: "/pinecall/token", body: { scope: "talk", resume: "kept" } },
    ]);
  });

  it("asks for the code a visitor keys, at a dev server's address when given one", async () => {
    const page = server({ "http://localhost:4747/pinecall/code": { status: 201, body: CODE } });
    expect(await hosted({ at: "http://localhost:4747/", fetch: page.fetch }).expect()).toEqual(CODE);
  });

  it("asks for a dictation's socket in the language the field is written in", async () => {
    const page = server({ "/pinecall/dictation": { status: 200, body: { url: "wss://gateway.example/v1/transcriptions/stream?token=t", hear: ["Riley"] } } });
    const { dictation } = hosted({ fetch: page.fetch });

    expect(await dictation("es")).toEqual({ url: "wss://gateway.example/v1/transcriptions/stream?token=t", hear: ["Riley"] });
    await dictation();
    expect(page.asked).toEqual([
      { path: "/pinecall/dictation", body: { language: "es" } },
      { path: "/pinecall/dictation", body: {} },
    ]);
  });

  it("fails with the server's own sentence, and with a plain one for a ticket it cannot read", async () => {
    const refusing = server({ "/pinecall/token": { status: 429, body: { detail: "too many calls from here: try again in a minute" } } });
    await expect(hosted({ fetch: refusing.fetch }).tokens("talk")).rejects.toThrow("too many calls from here");
    const odd = server({ "/pinecall/token": { status: 201, body: { call: "call_1" } } });
    await expect(hosted({ fetch: odd.fetch }).tokens("talk")).rejects.toThrow("a ticket this package does not know");
  });
});
