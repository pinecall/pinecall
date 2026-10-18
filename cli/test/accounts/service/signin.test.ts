/** Signing a machine in: a pairing opened with no key, the key collected once approved and proved; the org chosen, its key kept. */

import { existsSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../../src/accounts/service/index.js";
import { answer, GATEWAY, refuse } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder } from "../../support/project.js";

const WHO = { org: "org_1", slug: "clinica", key_id: "k_4f2a", label: "ana-macbook", env: "production", name: "Ana Ruiz", production: true };

describe("a sign-in", () => {
  it("opens a pairing with no key, collects the key, proves it, and keeps it at the gateway", async () => {
    const pairing = answer("post", "/v1/login/pairings", { code: "ABCD-1234" });
    const asked = answer("get", "/v1/login/pairings/:code/key", { key: "pc_live_machine" });
    const proved = answer("get", "/v1/whoami", WHO);
    const home = folder();
    const { ctx } = testContext({ home });
    const signIn = await service.startSignIn(ctx, service.StartSignInInput.parse({ gateway: `${GATEWAY}/`, waitS: 1 }));
    expect(signIn.link).toBe(`${GATEWAY}/cli?c=ABCD-1234`);
    expect(await signIn.done).toEqual({ gateway: GATEWAY, name: "Ana Ruiz", org: "clinica" });
    expect(pairing[0]!.authorization).toBeNull();
    expect(asked[0]!.query).toEqual({ wait_s: "1" });
    expect(proved[0]!.authorization).toBe("Bearer pc_live_machine");
    expect(service.readSignIn(home)).toEqual({ url: GATEWAY, key: "pc_live_machine", org: "clinica" });
  });

  it("asks again while nobody approved, and gives up once the time is up, keeping nothing", async () => {
    answer("post", "/v1/login/pairings", { code: "ABCD-1234" });
    const asked = answer("get", "/v1/login/pairings/:code/key", null);
    const home = folder();
    const { ctx } = testContext({ home });
    const signIn = await service.startSignIn(ctx, service.StartSignInInput.parse({ gateway: GATEWAY, waitS: 0.01, untilMs: 100 }));
    await expect(signIn.done).rejects.toThrow(service.TOOK_TOO_LONG);
    expect(asked.length).toBeGreaterThan(1);
    expect(signIn.outcome).toEqual({ failed: service.TOOK_TOO_LONG });
    expect(existsSync(join(home, "session.json"))).toBe(false);
  });
});

describe("the orgs", () => {
  it("lists only the orgs the person is a member of", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_9", slug: "acme", here: false, member: false }] });
    const { ctx } = testContext();
    expect((await service.listOrgs(ctx, { url: GATEWAY, key: "pc_live_machine" })).map(service.slugOf)).toEqual(["clinica"]);
  });

  it("chooses the only org, the one named, or names every one", () => {
    const orgs = [{ org: "org_1", slug: "clinica", here: true }, { org: "org_2", slug: null, here: false }];
    expect(service.chooseOrg([orgs[0]!], undefined)).toBe(orgs[0]);
    expect(service.chooseOrg(orgs, "org_2")).toBe(orgs[1]);
    expect(() => service.chooseOrg(orgs, undefined)).toThrow("which org is this project? pinecall new … --org clinica | org_2");
    expect(() => service.chooseOrg(orgs, "acme")).toThrow("you are no member of acme at this gateway: yours are clinica, org_2");
  });

  it("asks the gateway what it gives the org, and says nothing when it does not answer", async () => {
    answer("get", "/v1/providers/advice", { stages: [{ stage: "llm", choice: "openai/nemotron", runs_on: "served here", served: ["nemotron"] }], lends: [], judge: null, caller: null, machine: null });
    expect((await service.adviceAt(GATEWAY, "pc_live_machine"))?.stages[0]?.choice).toBe("openai/nemotron");
    refuse("get", "/v1/providers/advice", 404, "Not Found");
    expect(await service.adviceAt(GATEWAY, "pc_live_machine")).toBeNull();
  });
});
