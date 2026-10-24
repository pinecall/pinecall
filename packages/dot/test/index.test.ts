// The two public surfaces, pinned by name: adding an export means editing a list here on purpose.

import { describe, expect, it } from "vitest";

import * as agent from "../src/agent/index.js";
import * as page from "../src/index.js";

describe("the public surfaces", () => {
  it("@pinecall/dot is the face, the page as the agent reads it, and the tutor", () => {
    expect(Object.keys(page).sort()).toEqual(["Page", "face", "tutor"]);
  });

  it("@pinecall/dot/agent is the Tutor class, the macros it is given, and the walk a name means", () => {
    expect(Object.keys(agent).sort()).toEqual(["Tutor", "macros", "walkNamed"]);
  });
});
