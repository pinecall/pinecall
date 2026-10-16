/** Signing a machine in: a pairing opened with no key, the key collected once approved, proved, and only then kept. */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../../src/accounts/service/index.js";
import { answer, GATEWAY } from "../../support/gateway.js";
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
    expect(await signIn.done).toEqual({ gateway: GATEWAY, name: "Ana Ruiz" });
    expect(pairing[0]!.authorization).toBeNull();
    expect(asked[0]!.query).toEqual({ wait_s: "1" });
    expect(proved[0]!.authorization).toBe("Bearer pc_live_machine");
    expect(service.readSignIn(home)).toEqual({ url: GATEWAY, key: "pc_live_machine" });
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

describe("link", () => {
  it("lists only the orgs the person is a member of", async () => {
    answer("get", "/v1/login/orgs", { orgs: [{ org: "org_1", slug: "clinica", here: true }, { org: "org_9", slug: "acme", here: false, member: false }] });
    const { ctx } = testContext();
    expect((await service.listOrgs(ctx, { url: GATEWAY, key: "pc_live_machine" })).map(service.slugOf)).toEqual(["clinica"]);
  });

  it("chooses the only org, the one named, or names every one", () => {
    const orgs = [{ org: "org_1", slug: "clinica", here: true }, { org: "org_2", slug: null, here: false }];
    expect(service.chooseOrg([orgs[0]!], undefined)).toBe(orgs[0]);
    expect(service.chooseOrg(orgs, "org_2")).toBe(orgs[1]);
    expect(() => service.chooseOrg(orgs, undefined)).toThrow("which org is this project? --org clinica | org_2");
    expect(() => service.chooseOrg(orgs, "acme")).toThrow("you are no member of acme");
  });

  it("writes the machine's own key when it is already the org's, and the gateway beside it", async () => {
    const root = folder();
    const { ctx } = testContext({ cwd: root });
    const linked = await service.linkProject(ctx, { url: GATEWAY, key: "pc_live_machine" }, { org: "org_1", slug: "clinica", here: true });
    expect(linked).toMatchObject({ org: "clinica", written: ["PINECALL_KEY", "PINECALL_URL"] });
    expect(readFileSync(join(root, ".env"), "utf8")).toContain("PINECALL_KEY=pc_live_machine");
  });

  it("mints a key in another org, leaving the rest of .env as it was", async () => {
    const minted = answer("post", "/v1/login/org", { key: "pc_live_acme" });
    const root = folder();
    const { ctx } = testContext({ cwd: root });
    await service.linkProject(ctx, { url: GATEWAY, key: "pc_live_machine" }, { org: "org_2", slug: "acme", here: false });
    expect(minted[0]!.body).toEqual({ org: "org_2" });
    expect(minted[0]!.env).toBe("production");
    expect(readFileSync(join(root, ".env"), "utf8")).toContain("PINECALL_KEY=pc_live_acme");
  });
});
