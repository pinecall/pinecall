// The two public surfaces, pinned by name: adding an export means editing a list here on purpose.

import { describe, expect, it } from "vitest";

import * as agent from "../src/agent/index.js";
import * as page from "../src/index.js";
import * as server from "../src/server/index.js";

describe("the public surfaces", () => {
  it("@pinecall/dot is the face, the page as the agent reads it, and the tutor", () => {
    expect(Object.keys(page).sort()).toEqual(["Page", "face", "tutor"]);
  });

  it("@pinecall/dot/agent is the Tutor class, the macros it is given, and the walk a name means", () => {
    expect(Object.keys(agent).sort()).toEqual(["Tutor", "macros", "walkNamed"]);
  });

  it("@pinecall/dot/server is the site's door, what it decides, picks and records with, and the parts it is made of", () => {
    expect(Object.keys(server).sort()).toEqual(["answer", "decide", "decisionFrom", "pickRow", "questionsOf", "recordSay", "spansOf", "thingsOf"]);
  });
});
