/** A project's .env found from a folder up, read, and written leaving every other line. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { nearestDotenv, readDotenv, writeDotenv } from "../../src/kit/dotenv.js";
import { folder, write } from "../support/project.js";

describe(".env", () => {
  it("is found from a folder up, read with quotes and export, and written leaving every other line as it was", () => {
    const root = folder();
    const file = write(root, ".env", '# keys\nexport PINECALL_KEY="old"\nOTHER=1\n');
    const deep = join(root, "agents", "front-desk");
    write(root, "agents/front-desk/agent.ts", "");
    expect(nearestDotenv(deep)).toBe(file);
    expect(readDotenv(file)).toEqual({ PINECALL_KEY: "old", OTHER: "1" });
    writeDotenv(file, { PINECALL_KEY: "new", PINECALL_URL: "https://gw" });
    expect(readFileSync(file, "utf8")).toBe("# keys\nPINECALL_KEY=new\nOTHER=1\nPINECALL_URL=https://gw\n");
  });
});
