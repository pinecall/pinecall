/** Where the key and the gateway come from: the environment, else the nearest .env; and a token's env by its prefix. */

import { describe, expect, it } from "vitest";

import { CLOUD_URL, readCredentials, serverEnvOf } from "../../src/project/credentials.js";
import { folder, write } from "../support/project.js";

describe("the credentials", () => {
  it("the environment wins over .env, and v1's variable is never read", () => {
    const root = folder();
    write(root, ".env", "PINECALL_KEY=from-dotenv\n");
    expect(readCredentials({ PINECALL_KEY: "from-env" }, root)).toEqual({ url: CLOUD_URL, key: "from-env", source: "the environment" });
    expect(readCredentials({ PINECALL_API_KEY: "v1" }, folder()).key).toBeUndefined();
    expect(readCredentials({}, root)).toEqual({ url: CLOUD_URL, key: "from-dotenv", source: ".env" });
  });

  it("only the sandbox's prefix says a token's env", () => {
    expect([serverEnvOf("pc_test_x"), serverEnvOf("pc_live_x")]).toEqual(["sandbox", undefined]);
  });
});
