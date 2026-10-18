/** `pinecall new | generate` as typed: the files, the pinecall.json naming where the project runs, the next steps. */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { answer, GATEWAY, refuse } from "../support/gateway.js";
import { folder, project } from "../support/project.js";
import { run } from "../support/run.js";

/** A machine signed in to the fake gateway: its `~/.pinecall`. */
function signedIn(): string {
  const home = folder();
  writeFileSync(join(home, "session.json"), JSON.stringify({ gateways: { [GATEWAY]: { key: "pc_live_machine", org: "clinica" } }, last: GATEWAY }));
  return home;
}

describe("pinecall new", () => {
  it("writes ./<name> with no key at all, and prints the next steps: the first agent among them", async () => {
    const here = folder();
    const ran = await run(["new", "clinica-dental"], { cwd: here, key: null });
    expect(ran.code).toBe(0);
    expect(existsSync(join(here, "clinica-dental/agents"))).toBe(true);
    expect(ran.out).toContain("▸ clinica-dental · a TypeScript project, no agent yet");
    expect(ran.out).toContain("  pinecall generate agent <name>");
    expect(ran.out).toContain("  npm install");
    expect(ran.out).toContain("  pinecall login       sign this machine in; the project runs in your org");
    expect(existsSync(join(here, "clinica-dental/pinecall.json"))).toBe(false);
  });

  it("--agent writes the first agent in its own folder", async () => {
    const here = folder();
    const ran = await run(["new", "clinica-dental", "--agent", "sofia"], { cwd: here, key: null });
    expect(ran.code).toBe(0);
    expect(existsSync(join(here, "clinica-dental/agents/sofia/agent.tsx"))).toBe(true);
    expect(ran.out).toContain("▸ clinica-dental · a TypeScript project · agents/sofia/");
    expect(ran.out).not.toContain("generate agent");
  });

  it("--ruby writes a Ruby project, and two languages are refused", async () => {
    const here = folder();
    expect((await run(["new", "sales", "--ruby"], { cwd: here })).out).toContain("bundle install");
    expect((await run(["new", "other", "--ruby", "--python"], { cwd: here })).code).toBe(2);
  });

  it("on a signed-in machine, writes pinecall.json: the gateway, and the person's only org", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }] });
    const here = folder();
    const ran = await run(["new", "clinica-dental"], { cwd: here, key: null, env: { PINECALL_HOME: signedIn() } });
    expect(ran.code).toBe(0);
    expect(JSON.parse(readFileSync(join(here, "clinica-dental/pinecall.json"), "utf8"))).toEqual({ gateway: GATEWAY, org: "clinica" });
    expect(ran.out).toContain(`  runs in clinica at ${GATEWAY} (pinecall.json)`);
    expect(ran.out).not.toContain("pinecall login");
  });

  it("with several orgs and nobody to ask, names them and writes nothing; --org picks one and makes this machine's key there", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_2", slug: "acme", here: false }] });
    const minted = answer("post", "/v1/login/org", { key: "pc_live_acme" });
    const here = folder();
    const home = signedIn();
    const refused = await run(["new", "clinica-dental"], { cwd: here, key: null, env: { PINECALL_HOME: home } });
    expect(refused.code).toBe(2);
    expect(refused.err).toContain("--org clinica | acme");
    expect(existsSync(join(here, "clinica-dental"))).toBe(false);
    const ran = await run(["new", "clinica-dental", "--org", "acme"], { cwd: here, key: null, env: { PINECALL_HOME: home } });
    expect(ran.code).toBe(0);
    expect(JSON.parse(readFileSync(join(here, "clinica-dental/pinecall.json"), "utf8")).org).toBe("acme");
    expect(minted[0]!.body).toEqual({ org: "org_2" });
    expect(JSON.parse(readFileSync(join(home, "session.json"), "utf8")).gateways[GATEWAY].orgs).toEqual({ acme: "pc_live_acme" });
  });

  it("writes the project and says why when the gateway signed in to does not answer", async () => {
    refuse("get", "/v1/login/orgs", 503, "down");
    const here = folder();
    const ran = await run(["new", "clinica-dental"], { cwd: here, key: null, env: { PINECALL_HOME: signedIn() } });
    expect(ran.code).toBe(0);
    expect(ran.err).toContain("did not say your orgs");
    expect(existsSync(join(here, "clinica-dental/pinecall.json"))).toBe(false);
  });

  it("refuses a name the gateway would not take", async () => {
    expect((await run(["new", "FrontDesk"], { cwd: folder() })).code).toBe(2);
  });
});

describe("pinecall generate", () => {
  it("agent writes a second agent and says each file", async () => {
    const root = project(["front-desk"]);
    const ran = await run(["generate", "agent", "sales"], { cwd: root });
    expect(ran.code).toBe(0);
    expect(ran.out).toContain(`  wrote ${join("agents", "sales", "agent.tsx")}`);
  });

  it("g golden takes the lines in order and the tools", async () => {
    const root = project(["front-desk"]);
    const ran = await run(["g", "golden", "asks-for-a-refund", "--say", "Hi, I want a refund.", "--say", "It's Ana Ruiz.", "--tool", "takeMessage"], { cwd: root, key: null });
    expect(ran.code).toBe(0);
    expect(ran.out).toBe(`  wrote ${join("agents", "front-desk", "test", "goldens", "asks-for-a-refund.json")}\n`);
    expect(JSON.parse(readFileSync(join(root, "agents/front-desk/test/goldens/asks-for-a-refund.json"), "utf8")).turns).toEqual([{ say: "Hi, I want a refund." }, { say: "It's Ana Ruiz." }]);
  });

  it("golden needs --say", async () => {
    expect((await run(["generate", "golden", "x"])).code).toBe(2);
  });
});
