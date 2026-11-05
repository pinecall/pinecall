// A person's phone reaches one thing at a time: nothing until it is said, the one agent the org
// holds, the agent they named, their own copy when they hold one — and the sentence says which.

import { describe, expect, it } from "vitest";

import { readLine, whatAPhoneReaches, type Line } from "../src/lib/line";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime agents/schemas.py: TestNumbers, as GET /v1/line/numbers answers it.
const THE_LINE = { calling: ["+34600000000"], agent: null, test_line: "+13617334133", numbers: [{ number: "+12186633772", agent: "front" }] };

function answering(body: unknown, sent: { path: string; headers: Record<string, string> }[]): void {
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    sent.push({ path: String(url), headers: Object.fromEntries(new Headers(init?.headers).entries()) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

describe("the line is read in the sandbox, whichever console asks", () => {
  it("parses the runtime's shape and says the sandbox in the world header", async () => {
    const sent: { path: string; headers: Record<string, string> }[] = [];
    answering(THE_LINE, sent);
    const line = await readLine({ ...CREDENTIALS, world: "production" });
    expect(line.test_line).toBe("+13617334133");
    expect(line.numbers[0]?.agent).toBe("front");
    expect(sent[0]?.path).toContain("/v1/line/numbers");
    expect(sent[0]?.headers["pinecall-env"]).toBe("sandbox");
  });
});

describe("what a call from the phone reaches", () => {
  const line = (changes: Partial<Line> = {}): Line => ({ ...THE_LINE, ...changes });

  it("is nothing until the phone is said", () => {
    expect(whatAPhoneReaches(line({ calling: [] }), ["front"], []).tone).toBe("gray");
  });

  it("is the one agent the org holds when none was named, and a pick when it holds several", () => {
    expect(whatAPhoneReaches(line(), ["front"], [])).toEqual({ tone: "green", said: "front, as the org runs it in the sandbox." });
    expect(whatAPhoneReaches(line(), ["front", "sales"], []).said).toMatch(/pick the one/);
    expect(whatAPhoneReaches(line(), [], []).said).toMatch(/No agent is running/);
  });

  it("is the agent named, their own copy when they hold one, and nothing when nobody runs it", () => {
    expect(whatAPhoneReaches(line({ agent: "sales" }), ["front", "sales"], ["sales"]).said).toBe("Your own copy of sales, the one pinecall start holds.");
    expect(whatAPhoneReaches(line({ agent: "sales" }), ["front", "sales"], []).said).toBe("sales, as the org runs it in the sandbox.");
    expect(whatAPhoneReaches(line({ agent: "sales" }), ["front"], []).tone).toBe("amber");
  });
});
