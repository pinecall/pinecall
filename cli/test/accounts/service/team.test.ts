/** The org's people: a password sent once for the member the address names, a reset link answered, an unknown address refused by name. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/accounts/service/index.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";

const ANA = { id: "m_ana", email: "ana@clinica.com", name: "Ana", role: "admin", status: "active", operator: true, production: true };
const LUIS = { ...ANA, id: "m_luis", email: "luis@clinica.com", name: "Luis", role: "qa", status: "invited", operator: false };

describe("team", () => {
  it("sends the password once, to the member the address names, whatever its case", async () => {
    answer("get", "/v1/members", { members: [ANA, LUIS] });
    const sent = answer("put", "/v1/members/:id/password", { ...LUIS, status: "active" });
    const { ctx } = testContext();
    const set = await service.setTeamPassword(ctx, { email: "Luis@Clinica.com", password: "a long one" });
    expect(set.status).toBe("active");
    expect(sent[0]!.path).toBe("/v1/members/m_luis/password");
    expect(sent[0]!.body).toEqual({ password: "a long one" });
  });

  it("refuses an empty password and an address nobody in the org has, sending nothing", async () => {
    answer("get", "/v1/members", { members: [ANA] });
    const { ctx } = testContext();
    await expect(service.setTeamPassword(ctx, { email: "ana@clinica.com", password: "" })).rejects.toThrow("no password for ana@clinica.com");
    await expect(service.setTeamPassword(ctx, { email: "nobody@clinica.com", password: "x" })).rejects.toThrow("nobody with the address nobody@clinica.com");
  });

  it("answers the one-use link the gateway handed over", async () => {
    answer("get", "/v1/members", { members: [ANA] });
    answer("post", "/v1/members/:id/reset", { member: ANA, token: "t", link: "https://box/invitations/inv_x", mailed: false });
    const { ctx } = testContext();
    expect(await service.resetLink(ctx, "ana@clinica.com")).toEqual({ email: "ana@clinica.com", link: "https://box/invitations/inv_x", mailed: false });
  });
});
