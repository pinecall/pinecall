/** `pinecall.json`: found from any folder of the project, written at its root, and said by name when it is wrong. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { findProjectConfig, writeProjectConfig } from "../../src/project/config.js";
import { folder, write } from "../support/project.js";

describe("pinecall.json", () => {
  it("is written at the root without a trailing slash, and found from a folder deep in the project", () => {
    const root = folder();
    const file = writeProjectConfig(root, { gateway: "https://pinecall.example.com/", org: "clinica" });
    expect(JSON.parse(readFileSync(file, "utf8"))).toEqual({ gateway: "https://pinecall.example.com", org: "clinica" });
    write(root, "agents/front-desk/agent.tsx", "");
    expect(findProjectConfig(join(root, "agents", "front-desk"))).toEqual({ config: { gateway: "https://pinecall.example.com", org: "clinica" }, file });
    expect(findProjectConfig(folder())).toBeUndefined();
  });

  it("is refused by name when it is not JSON, or names no gateway or no org", () => {
    const root = folder();
    write(root, "pinecall.json", "{not json");
    expect(() => findProjectConfig(root)).toThrow("is not JSON");
    write(root, "pinecall.json", JSON.stringify({ org: "clinica" }));
    expect(() => findProjectConfig(root)).toThrow("names the project's gateway and org");
    write(root, "pinecall.json", JSON.stringify({ gateway: "https://x.example.com", org: "clinica", key: "pc_live_x" }));
    expect(() => findProjectConfig(root)).toThrow("names the project's gateway and org");
  });
});
