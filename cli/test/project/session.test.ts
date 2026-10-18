/** `~/.pinecall/session.json`: a sign-in per gateway with its org, the keys minted in other orgs, owner-only. */

import { statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { keepOrgKey, keepSignIn, keyIn, readSession, readSignIn, SESSION_FILE, writeCallerNumber } from "../../src/project/session.js";
import { folder } from "../support/project.js";

const GW = "https://pinecall.example.com";

describe("the session", () => {
  it("keeps a sign-in per gateway, the last one named, readable by its owner alone", () => {
    const home = folder();
    keepSignIn(home, GW, "pc_live_signin", "clinica");
    keepSignIn(home, "http://127.0.0.1:8080", "pc_live_local", "default");
    expect(readSignIn(home)).toEqual({ url: "http://127.0.0.1:8080", key: "pc_live_local", org: "default" });
    expect(readSignIn(home, GW)).toEqual({ url: GW, key: "pc_live_signin", org: "clinica" });
    expect(statSync(join(home, SESSION_FILE)).mode & 0o777).toBe(0o600);
  });

  it("answers this machine's key in an org: the sign-in's in its own, a minted one in another, none in a third", () => {
    const home = folder();
    keepSignIn(home, GW, "pc_live_signin", "clinica");
    keepOrgKey(home, GW, "acme", "pc_live_acme");
    expect([keyIn(home, GW, "clinica"), keyIn(home, GW, "acme"), keyIn(home, GW, "dental")]).toEqual(["pc_live_signin", "pc_live_acme", undefined]);
  });

  it("a new sign-in drops the keys minted from the old one and keeps the phone", () => {
    const home = folder();
    keepSignIn(home, GW, "pc_live_old", "clinica");
    keepOrgKey(home, GW, "acme", "pc_live_acme");
    writeCallerNumber(home, GW, "+59899123456");
    keepSignIn(home, GW, "pc_live_new", "clinica");
    expect(readSession(home).gateways[GW]).toEqual({ key: "pc_live_new", org: "clinica", calling: "+59899123456" });
  });
});
