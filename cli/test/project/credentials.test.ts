/** Where the key and the gateway come from: the environment, the nearest .env, the project's pinecall.json and this machine's sign-in; a token's env by its prefix. */

import { describe, expect, it } from "vitest";

import { CLOUD_URL, NO_KEY, prepareProjectKey, readCredentials, serverEnvOf } from "../../src/project/credentials.js";
import { readSession, SESSION_FILE } from "../../src/project/session.js";
import { answer, GATEWAY } from "../support/gateway.js";
import { folder, write } from "../support/project.js";

/** A machine signed in to the fake gateway in `clinica`, with a key minted in `acme` before. */
function signedIn(): string {
  const home = folder();
  write(home, SESSION_FILE, JSON.stringify({ gateways: { [GATEWAY]: { key: "pc_live_signin", org: "clinica", orgs: { acme: "pc_live_acme" } } }, last: GATEWAY }));
  return home;
}

/** A project whose pinecall.json runs it in an org of the fake gateway. */
function projectIn(org: string, gateway = GATEWAY): string {
  const root = folder();
  write(root, "pinecall.json", JSON.stringify({ gateway, org }));
  write(root, "agents/front-desk/agent.tsx", "");
  return root;
}

describe("the credentials", () => {
  it("the environment wins over .env, .env over everything of this machine, and v1's variable is never read", () => {
    const root = projectIn("clinica");
    write(root, ".env", "PINECALL_KEY=from-dotenv\n");
    expect(readCredentials({ PINECALL_KEY: "from-env" }, root, signedIn())).toEqual({ url: CLOUD_URL, key: "from-env", source: "the environment" });
    expect(readCredentials({}, root, signedIn())).toEqual({ url: CLOUD_URL, key: "from-dotenv", source: ".env" });
    expect(readCredentials({ PINECALL_API_KEY: "v1" }, folder(), folder()).key).toBeUndefined();
  });

  it("a project runs where its pinecall.json says, on this machine's key in that org, from any folder of it", () => {
    const home = signedIn();
    const session = `your sign-in (${home}/${SESSION_FILE})`;
    expect(readCredentials({}, projectIn("clinica"), home)).toEqual({ url: GATEWAY, key: "pc_live_signin", source: session, org: "clinica" });
    expect(readCredentials({}, `${projectIn("acme")}/agents/front-desk`, home)).toEqual({ url: GATEWAY, key: "pc_live_acme", source: session, org: "acme" });
  });

  it("says what to do when this machine has no key where the project runs", () => {
    const home = signedIn();
    expect(readCredentials({}, projectIn("dental"), home).missing).toContain("this machine has no key in dental at");
    expect(readCredentials({}, projectIn("clinica", "https://pinecall.example.com"), home).missing).toContain("sign in there, `pinecall login https://pinecall.example.com`");
    const broken = folder();
    write(broken, "pinecall.json", "{not json");
    expect(readCredentials({}, broken, home).missing).toContain("pinecall.json is not JSON");
  });

  it("outside a project, the sign-in at the gateway signed in to last, in its own org; signed in nowhere, nothing", () => {
    const home = signedIn();
    expect(readCredentials({}, folder(), home)).toMatchObject({ url: GATEWAY, key: "pc_live_signin", org: "clinica" });
    expect(readCredentials({}, folder(), folder())).toEqual({ url: CLOUD_URL, key: undefined, source: "nowhere", missing: NO_KEY });
  });

  it("before a verb, mints this machine's key in the project's org once and keeps it beside the sign-in", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_3", slug: "dental", here: false }] });
    const minted = answer("post", "/v1/login/org", { key: "pc_live_dental" });
    const home = signedIn();
    const root = projectIn("dental");
    await prepareProjectKey({}, root, home);
    expect(minted[0]!.body).toEqual({ org: "org_3" });
    expect(readSession(home).gateways[GATEWAY]?.orgs).toEqual({ acme: "pc_live_acme", dental: "pc_live_dental" });
    expect(readCredentials({}, root, home).key).toBe("pc_live_dental");
    await prepareProjectKey({}, root, home);
    expect(minted).toHaveLength(1);
  });

  it("only the sandbox's prefix says a token's env", () => {
    expect([serverEnvOf("pc_test_x"), serverEnvOf("pc_live_x")]).toEqual(["sandbox", undefined]);
  });
});
