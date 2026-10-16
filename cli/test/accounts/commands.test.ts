/** `pinecall login | link | whoami | secrets` as typed: the link printed, the key never; .env written; envs explained. */

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { answer, GATEWAY } from "../support/gateway.js";
import { folder } from "../support/project.js";
import { run } from "../support/run.js";

const WHO = { org: "org_1", slug: "clinica", key_id: "k_4f2a1d9c66b30e17", label: "ana-macbook", env: "sandbox", name: "Ana Ruiz", production: true };

/** A machine signed in to the fake gateway: its `~/.pinecall`. */
function signedInHome(): string {
  const home = folder();
  writeFileSync(join(home, "session.json"), JSON.stringify({ gateways: { [GATEWAY]: { key: "pc_live_machine" } }, last: GATEWAY }));
  return home;
}

describe("pinecall login", () => {
  it("prints the link on stderr, and who signed in once approved; the key nowhere", async () => {
    answer("post", "/v1/login/pairings", { code: "ABCD-1234" });
    answer("get", "/v1/login/pairings/:code/key", { key: "pc_live_machine" });
    answer("get", "/v1/whoami", { ...WHO, env: "production" });
    const ran = await run(["login", GATEWAY, "--no-open"]);
    expect(ran.code).toBe(0);
    expect(ran.err).toContain(`${GATEWAY}/cli?c=ABCD-1234`);
    expect(ran.out).toBe(`signed in to ${GATEWAY} as Ana Ruiz\n`);
    expect(ran.out + ran.err).not.toContain("pc_live_machine");
  });
});

describe("pinecall link", () => {
  it("writes the key of the only org into .env, and says so", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }] });
    const root = folder();
    const ran = await run(["link"], { cwd: root, key: null, env: { PINECALL_HOME: signedInHome() } });
    expect(ran.code).toBe(0);
    expect(ran.out).toBe("▸ clinica · PINECALL_KEY and PINECALL_URL written to .env\n");
    expect(readFileSync(join(root, ".env"), "utf8")).toContain("PINECALL_KEY=pc_live_machine");
  });

  it("with several orgs and nobody at the terminal, names them and refuses", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_2", slug: "acme", here: false }] });
    const ran = await run(["link"], { cwd: folder(), key: null, env: { PINECALL_HOME: signedInHome() } });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("--org clinica | acme");
  });

  it("--org mints a key in the org named", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_2", slug: "acme", here: false }] });
    const minted = answer("post", "/v1/login/org", { key: "pc_live_acme" });
    const ran = await run(["link", "--org", "acme"], { cwd: folder(), key: null, env: { PINECALL_HOME: signedInHome() } });
    expect(ran.code).toBe(0);
    expect(minted[0]!.body).toEqual({ org: "org_2" });
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
