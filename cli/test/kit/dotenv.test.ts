/** A project's .env found from a folder up, and read. */

import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { nearestDotenv, readDotenv } from "../../src/kit/dotenv.js";
import { folder, write } from "../support/project.js";

describe(".env", () => {
  it("is found from a folder up, and read with quotes and export", () => {
    const root = folder();
    const file = write(root, ".env", '# keys\nexport PINECALL_KEY="old"\nOTHER=1\n');
    const deep = join(root, "agents", "front-desk");
    write(root, "agents/front-desk/agent.ts", "");
    expect(nearestDotenv(deep)).toBe(file);
    expect(readDotenv(file)).toEqual({ PINECALL_KEY: "old", OTHER: "1" });
  });
});
