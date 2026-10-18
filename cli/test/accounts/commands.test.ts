/** `pinecall login | whoami | secrets` as typed: the link printed, the key never; the org chosen and kept; envs explained. */

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { answer, GATEWAY } from "../support/gateway.js";
import { folder } from "../support/project.js";
import { run } from "../support/run.js";

const WHO = { org: "org_1", slug: "clinica", key_id: "k_4f2a1d9c66b30e17", label: "ana-macbook", env: "sandbox", name: "Ana Ruiz", production: true };

const ADVICE = {
  stages: [
    { stage: "stt", choice: "openai/whisper", runs_on: "served here", served: ["whisper"] },
    { stage: "llm", choice: "openai/nemotron-3.5-lightning:30b-a3b", runs_on: "served here", served: ["nemotron-3.5-lightning:30b-a3b"] },
    { stage: "tts", choice: "cartesia", runs_on: "needs a key", served: [] },
  ],
  lends: [],
  judge: null,
  caller: null,
  machine: null,
};

/** A pairing approved at the fake gateway: the machine's key, and who it is. */
function approves(): void {
  answer("post", "/v1/login/pairings", { code: "ABCD-1234" });
  answer("get", "/v1/login/pairings/:code/key", { key: "pc_live_machine" });
  answer("get", "/v1/whoami", { ...WHO, env: "production" });
}

describe("pinecall login", () => {
  it("signs in, says the org and what the runtime gives; the key nowhere", async () => {
    approves();
    answer("get", "/v1/providers/advice", ADVICE);
    const home = folder();
    const ran = await run(["login", GATEWAY, "--no-open"], { env: { PINECALL_HOME: home } });
    expect(ran.code).toBe(0);
    expect(ran.err).toContain(`${GATEWAY}/cli?c=ABCD-1234`);
    expect(ran.out).toContain(`signed in to ${GATEWAY} as Ana Ruiz · org clinica`);
    expect(ran.out).toMatch(/thinking\s+openai\/nemotron-3\.5-lightning:30b-a3b\s+served here/);
    expect(ran.out).toContain("a stage that needs a key: pinecall providers add <vendor>");
    expect(ran.out + ran.err).not.toContain("pc_live_machine");
    expect(JSON.parse(readFileSync(join(home, "session.json"), "utf8")).gateways[GATEWAY]).toEqual({ key: "pc_live_machine", org: "clinica" });
  });

  it("is the one way in: link, setup and --org are none of this CLI's", async () => {
    for (const gone of [["link"], ["setup"], ["login", "--org", "acme"]]) {
      const ran = await run(gone);
      expect(ran.code).not.toBe(0);
      expect(ran.err).toMatch(/unknown command|unknown option/);
    }
  });

  it("leaves every verb on this machine running on the sign-in, in any folder", async () => {
    const sent = answer("get", "/v1/whoami", WHO);
    const home = folder();
    writeFileSync(join(home, "session.json"), JSON.stringify({ gateways: { [GATEWAY]: { key: "pc_live_machine", org: "clinica" } }, last: GATEWAY }));
    const ran = await run(["whoami"], { cwd: folder(), key: null, env: { PINECALL_HOME: home } });
    expect(ran.code).toBe(0);
    expect(ran.out.split("\n")[0]).toBe(`gateway ${GATEWAY} · org clinica · key from your sign-in (${home}/session.json) · sandbox`);
    expect(sent[0]!.authorization).toBe("Bearer pc_live_machine");
  });
});

describe("pinecall whoami", () => {
  it("prints the connection, who the key is, and which envs it opens", async () => {
    const sent = answer("get", "/v1/whoami", WHO);
    const ran = await run(["whoami"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toBe(
      [
        `gateway ${GATEWAY} · key from the environment · sandbox`,
        "  org clinica · key k_4f2a1d9c66b30e17 · sandbox · ana-macbook · production: yes",
        "  a person's key: the sandbox without --prod, production with it",
        "",
      ].join("\n"),
    );
    expect(sent[0]!.env).toBe("sandbox");
  });

  it("a sandbox server's token is refused with --prod before anything is sent", async () => {
    const ran = await run(["whoami", "--prod"], { key: "pc_test_server" });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("run the verb without --prod");
  });

  it("reads the key from the project's .env when the environment holds none", async () => {
    answer("get", "/v1/whoami", { ...WHO, name: null, label: null });
    const root = folder();
    writeFileSync(join(root, ".env"), `PINECALL_KEY=pc_live_from_dotenv\nPINECALL_URL=${GATEWAY}\n`);
    const ran = await run(["whoami"], { cwd: root, key: null, env: { PINECALL_URL: undefined } });
    expect(ran.out).toContain("key from .env");
    expect(ran.out).toContain("a sandbox server's token: that environment alone");
  });
});

describe("pinecall secrets", () => {
  it("set reads the whole of the pipe as the value", async () => {
    const sent = answer("put", "/v1/secrets/:name", { secrets: [] });
    const ran = await run(["secrets", "set", "TLS_KEY"], { stdin: "-----BEGIN-----\nabc\n-----END-----\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ value: "-----BEGIN-----\nabc\n-----END-----" });
    expect(ran.out).toBe("TLS_KEY kept · the org's hosted apps here start again with it\n");
  });

  it("set refuses a name of Pinecall's before reading anything", async () => {
    const ran = await run(["secrets", "set", "PINECALL_URL"], { stdin: "x" });
    expect(ran.code).toBe(2);
  });

  it("alone lists names, when and by whom; never a value", async () => {
    answer("get", "/v1/secrets", { secrets: [{ name: "CRM_TOKEN", set_by: "m_ana", set_at: 1_792_150_000 }] });
    const ran = await run(["secrets"]);
    expect(ran.out).toMatch(/^NAME\s+SET\s+BY\nCRM_TOKEN\s+\d{4}-\d{2}-\d{2} \d{2}:\d{2}\s+m_ana\n$/);
  });
});
