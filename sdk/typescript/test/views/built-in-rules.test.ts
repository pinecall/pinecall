// The framework's own words in identity: English rules for any agent, and the channel's block.

import { describe, expect, it } from "vitest";

import { Agent, CallWorld, promptOf, seal, setCall } from "../../src/index.js";
import { type Medium } from "../../src/wire/defs.js";

/** Agenda de la Clínica Norte. */
class Clinica extends Agent {}

/** Agenda que escribe sus propias normas de formato. */
class SinCanal extends Agent {
  override channelRules = false;
}

function identityOf(agent: Agent): string {
  return promptOf(agent).blocks.find((block) => block.name === "identity")!.text;
}

/** An agent serving a call on `channel`, with `medium` when the gateway said one. */
function serving(agent: Agent, channel: string, medium?: Medium): Agent {
  const line = medium === undefined ? { id: "CA_1", contact: "", channel } : { id: "CA_1", contact: "", channel, medium };
  setCall(agent, new CallWorld(line, () => undefined));
  return agent;
}

function channelOf(identity: string): string | undefined {
  return /<channel>\n([\s\S]*?)\n<\/channel>/.exec(identity)?.[1];
}

const SPOKEN = "You are on a phone call.";
const WEBSITE = "You are in a written chat on a website.";
const WHATSAPP = "You are on WhatsApp.";

describe("the rules and protocols", () => {
  it("are English for every agent, and tell it to answer in the caller's language", () => {
    const identity = identityOf(serving(seal(new Clinica()), "phone"));

    expect(identity).toContain("One question per turn");
    expect(identity).toContain("- Answer in the language the caller speaks.");
    expect(identity).toContain("To act, call a tool");
    expect(identity).not.toContain("Una sola pregunta");
  });

  it("leave how to write to the channel block, not to a rule", () => {
    const rules = /<rules>\n([\s\S]*?)\n<\/rules>/.exec(identityOf(seal(new Clinica())))?.[1];

    expect(rules).not.toContain("markdown");
    expect(rules).not.toContain("phone");
  });
});

describe("the channel block", () => {
  it.each([
    ["phone", "voice", SPOKEN],
    ["web", "voice", SPOKEN],
    ["web", "text", WEBSITE],
    ["whatsapp", "text", WHATSAPP],
    ["whatsapp", "voice", WHATSAPP],
  ] as const)("on %s by %s says how to write there", (channel, medium, opening) => {
    expect(channelOf(identityOf(serving(seal(new Clinica()), channel, medium)))).toMatch(new RegExp(`^${opening}`));
  });

  it.each([
    ["phone", SPOKEN],
    ["web", SPOKEN],
    ["whatsapp", WHATSAPP],
  ] as const)("takes the medium a %s call implies when the gateway does not say", (channel, opening) => {
    expect(channelOf(identityOf(serving(seal(new Clinica()), channel)))).toMatch(new RegExp(`^${opening}`));
  });

  it("is a phone call's when there is no call at all", () => {
    expect(channelOf(identityOf(seal(new Clinica())))).toMatch(new RegExp(`^${SPOKEN}`));
  });

  it("is the texts the framework ships, word for word", () => {
    expect(channelOf(identityOf(serving(seal(new Clinica()), "phone")))).toBe(
      "You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, " +
        "no lists, no bold, no symbols, no links. Say an email or a web address the way a person says it out loud.",
    );
    expect(channelOf(identityOf(serving(seal(new Clinica()), "web", "text")))).toBe(
      "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when there " +
        "are steps, bold for the one thing that matters.",
    );
    expect(channelOf(identityOf(serving(seal(new Clinica()), "whatsapp")))).toBe(
      "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages.",
    );
  });

  it("is left out on every channel for a class that sets channelRules = false", () => {
    for (const channel of ["phone", "web", "whatsapp"]) {
      const identity = identityOf(serving(seal(new SinCanal()), channel));
      expect(identity).not.toContain("<channel>");
      expect(identity).toContain("<protocols>");
    }
  });

  it("leaves the medium readable on the call when it is off", () => {
    const agent = serving(seal(new SinCanal()), "web", "text");

    expect(agent.call.medium).toBe("text");
  });
});
