/** A new account gets its first agent: made once in the sandbox, in Studio, so there is something to talk to on the first visit. */

import { useEffect } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { readHosted } from "./door";
import { makeStudioAgent, type FirstDefinition } from "./studio-door";

// A name belongs to one organization across the whole platform, so the first agent carries its org's: `acme-assistant`.
const LONGEST = 40;
const firstAgentOf = (org: string): string => `${org.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^[^a-z]+|-+$/g, "").slice(0, LONGEST - 10) || "my"}-assistant`;

// What it starts as: the gateway's own first instructions, and a greeting, so the first call opens with a voice and not with silence.
const FIRST: FirstDefinition = { instructions: "You answer the phone for the business. Be brief and friendly: everything you say is read aloud. Ask one question at a time.", greeting: { say: "Hello, thanks for calling. How can I help?" }, tools: [], collect: null };

const NEWBORN_UNDER = "pinecall.newborn";

/** Said when an account is made here: its first visit to the console is the one that gets the agent. */
export function markNewborn(): void {
  try {
    window.localStorage.setItem(NEWBORN_UNDER, "1");
  } catch {
    // A browser that keeps nothing: the Agents page's New makes the first one.
  }
}

function isNewborn(): boolean {
  try {
    return window.localStorage.getItem(NEWBORN_UNDER) === "1";
  } catch {
    return false;
  }
}

function grownUp(): void {
  try {
    window.localStorage.removeItem(NEWBORN_UNDER);
  } catch {
    // Nothing was kept.
  }
}

// Asked once per org and page: the frame is drawn twice in development, and an org is given one agent, not two.
const asked = new Set<string>();

/** Makes `<org>-assistant` for an account just made on this browser, when it holds no agent and hosts no app, in the sandbox alone; an account that was already there is never given one. */
export function useFirstAgent(): void {
  const credentials = useCredentials();
  const { whose, agents, agentsRead } = useOrg();
  const org = whose?.org ?? null;
  const slug = whose?.slug ?? null;
  const nothing = agentsRead && agents.length === 0;
  useEffect(() => {
    if (WORLD !== "sandbox" || org === null || !agentsRead || asked.has(org) || !isNewborn()) return;
    // Read once, whatever it finds: the account is no longer new after its first visit.
    grownUp();
    if (!nothing) return;
    asked.add(org);
    void (async () => {
      try {
        if ((await readHosted(credentials)).length > 0) return;
        await makeStudioAgent(credentials, firstAgentOf(slug ?? org), FIRST);
      } catch {
        // Refused: the Agents page says there is none, and New makes one.
      }
    })();
  }, [credentials, org, slug, agentsRead, nothing]);
}
