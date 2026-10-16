/** The org's secrets: a name an environment variable's and never Pinecall's, a value sent once and never read back. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/accounts/service/index.js";
import { UsageError } from "../../../src/errors.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";

describe("secrets", () => {
  it("refuses a name that is no environment variable's, or one Pinecall sets", () => {
    expect(() => service.checkSecretName("crm_token")).toThrow(UsageError);
    expect(() => service.checkSecretName("PINECALL_KEY")).toThrow("PINECALL_KEY is Pinecall's to set");
    expect(() => service.checkSecretName("CRM_TOKEN")).not.toThrow();
  });

  it("sends the value once and answers the name alone", async () => {
    const sent = answer("put", "/v1/secrets/:name", { secrets: [] });
    const { ctx } = testContext({ env: "production" });
    expect(await service.setSecret(ctx, { name: "CRM_TOKEN", value: "line one\nline two" })).toEqual({ name: "CRM_TOKEN" });
    expect(sent[0]!.body).toEqual({ value: "line one\nline two" });
    expect(sent[0]!.env).toBe("production");
  });

  it("refuses an empty value without sending it", async () => {
    const { ctx } = testContext();
    await expect(service.setSecret(ctx, { name: "CRM_TOKEN", value: "" })).rejects.toThrow("no value for CRM_TOKEN");
  });
});

describe("whoami", () => {
  it("names the org by its slug, else its id, and the person by name, label, or a stand-in", () => {
    expect(service.orgOf({ org: "org_1", slug: "clinica" })).toBe("clinica");
    expect(service.orgOf({ org: "org_1", slug: null })).toBe("org_1");
    const who = { org: "org_1", key_id: "k_1", label: null, env: "sandbox", production: false };
    expect(service.personOf({ ...who, name: "Ana" })).toBe("Ana");
    expect(service.personOf({ ...who, label: "ci" })).toBe("ci");
    expect(service.personOf(who)).toBe("this key's person");
  });
});
