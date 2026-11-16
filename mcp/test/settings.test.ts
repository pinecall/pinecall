/** The settings read off the environment: the two addresses required and bare, the port a port. */

import { describe, expect, it } from "vitest";

import { DEFAULT_PORT, readSettings } from "../src/settings.js";

const SAID = { PINECALL_MCP_URL: "https://mcp.example.com", PINECALL_URL: "https://cloud.example.com/" };

describe("the settings", () => {
  it("are the two addresses with no path, and the port unless one is said", () => {
    expect(readSettings(SAID)).toEqual({ port: DEFAULT_PORT, address: "https://mcp.example.com", gateway: "https://cloud.example.com" });
    expect(readSettings({ ...SAID, PINECALL_MCP_PORT: "9000" }).port).toBe(9000);
  });

  it("carry OpenAI's domain challenge only when one is set", () => {
    expect(readSettings(SAID).openaiChallenge).toBeUndefined();
    expect(readSettings({ ...SAID, PINECALL_MCP_OPENAI_CHALLENGE: " oai-token-1 \n" }).openaiChallenge).toBe("oai-token-1");
  });

  it("name the variable that is missing, has a path, or is no port", () => {
    expect(() => readSettings({ PINECALL_URL: SAID.PINECALL_URL })).toThrow(/PINECALL_MCP_URL is not set/);
    expect(() => readSettings({ ...SAID, PINECALL_URL: "cloud.example.com" })).toThrow(/PINECALL_URL is cloud.example.com/);
    expect(() => readSettings({ ...SAID, PINECALL_MCP_URL: "https://mcp.example.com/mcp" })).toThrow(/with no path/);
    expect(() => readSettings({ ...SAID, PINECALL_MCP_PORT: "http" })).toThrow(/PINECALL_MCP_PORT is http/);
  });
});
