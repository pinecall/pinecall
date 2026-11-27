/** What kind of conversation a row is, and how it is said: a phone call, a web call, a website's chat, WhatsApp, SMS, an email thread, Messenger, Instagram; and which rows are tests. */

import { isARun, isSimulated } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";

export type Kind = "phone" | "web-call" | "web-chat" | "whatsapp" | "sms" | "email" | "messenger" | "instagram";

type Row = Pick<SessionLine, "channel" | "spoken">;

// A web call by voice and a website's chat are both `web`: the list says which is spoken.
/** What kind of conversation a row is. */
export function typeOf(line: Row): Kind {
  if (line.channel === "whatsapp" || line.channel === "sms" || line.channel === "email" || line.channel === "messenger" || line.channel === "instagram") return line.channel;
  if (line.channel === "web") return line.spoken === true ? "web-call" : "web-chat";
  return "phone";
}

const SAID: Record<Kind, string> = { phone: "phone", "web-call": "web call", "web-chat": "web chat", whatsapp: "WhatsApp", sms: "SMS", email: "email", messenger: "Messenger", instagram: "Instagram" };
const NAMED: Record<Kind, string> = { phone: "Phone call", "web-call": "Web call", "web-chat": "Web chat", whatsapp: "WhatsApp conversation", sms: "SMS conversation", email: "Email thread", messenger: "Messenger conversation", instagram: "Instagram conversation" };
const GOING: Record<Kind, string> = { phone: "On a call now", "web-call": "On a call now", "web-chat": "Chatting now", whatsapp: "Open, waiting for a reply", sms: "Open, waiting for a reply", email: "Open, waiting for a reply", messenger: "Open, waiting for a reply", instagram: "Open, waiting for a reply" };

/** A row's kind in a word or two, among rows of every kind: `web chat`, `WhatsApp`. */
export function kindSaid(line: Row): string {
  return SAID[typeOf(line)];
}

/** A row's kind as a sentence starts with it: `Web chat`, `Email thread`. */
export function kindNamed(line: Row): string {
  return NAMED[typeOf(line)];
}

/** What a row that has not ended is doing: on a call, chatting, or open and waiting for its contact. */
export function goingSaid(line: Row): string {
  return GOING[typeOf(line)];
}

/** What a row is, in its own word: a call, a conversation, an email thread. */
export function thingOf(line: Row): string {
  const type = typeOf(line);
  return type === "email" ? "email thread" : type === "phone" || type === "web-call" ? "call" : "conversation";
}

/** Whether a row is a test: a simulated caller's call or a golden's run, never a person's. Hidden unless asked for. */
export function isATest(line: Pick<SessionLine, "from" | "run">): boolean {
  return isSimulated(line) || isARun(line);
}
