/** The console's addresses: production's at the root, the sandbox's under /sandbox, a one-use code and never the key. */

import { describe, expect, it } from "vitest";

import { consoleAddress, consoleUrl, TALK, whyNoConsole } from "../../src/dev/console.js";
import { GatewayError } from "../../src/errors.js";

describe("the console", () => {
  it("is at the root in production and under /sandbox otherwise, an agent's screen by its slug", () => {
    expect(consoleUrl("https://cloud.pinecall.io/", "production", undefined, "c+1")).toBe("https://cloud.pinecall.io/?login=c%2B1");
    expect(consoleUrl("https://cloud.pinecall.io", "sandbox", "front-desk", "abc", TALK)).toBe("https://cloud.pinecall.io/sandbox/a/front-desk/playground?login=abc");
    expect(consoleAddress("https://cloud.pinecall.io", "sandbox", "front-desk")).toBe("https://cloud.pinecall.io/sandbox/a/front-desk");
  });

  it("an older gateway with no login codes is told to restart; any other failure in its own words", () => {
    expect(whyNoConsole(new GatewayError(404, "Not Found"))).toMatch(/older than this CLI/);
    expect(whyNoConsole(new GatewayError(403, "no"))).toBe("the gateway answered 403: no");
    expect(whyNoConsole(new Error("offline"))).toBe("offline");
  });
});
