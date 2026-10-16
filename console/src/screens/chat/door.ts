/** Chat requests to the agent's `pinecall start` process: class, open, turn, hang up. */

import { z } from "zod";

import type { Credentials } from "@pinecall/core/api";
import { dev } from "../../lib/dev";

/** The agent class available in the `pinecall start` directory. */
const RosterSchema = z.object({ agent: z.string().nullable(), states: z.array(z.string()) });
export type Roster = z.infer<typeof RosterSchema>;

const CallSchema = z.object({ call: z.string() });

/** The class mounted by the process holding this agent, if any. */
export async function readChatRoster(credentials: Credentials, agent: string): Promise<Roster> {
  return RosterSchema.parse(await dev(credentials, agent, "chat.roster"));
}

/**
 * Open a text call. `as` sets the contact (for memory); `golden` starts from that golden's state,
 * like `pinecall chat --state`.
 */
export async function startChat(
  credentials: Credentials,
  agent: string,
  as: string,
  golden: string,
): Promise<string> {
  const body = { agent, ...(as === "" ? {} : { as }), ...(golden === "" ? {} : { golden }) };
  return CallSchema.parse(await dev(credentials, agent, "chat.start", body)).call;
}

/** Send one user turn; the reply arrives on the call's log. */
export async function sayInChat(credentials: Credentials, agent: string, call: string, text: string): Promise<void> {
  CallSchema.parse(await dev(credentials, agent, "chat.say", { call, text }));
}

/** Hang up; closing the socket seals the log and runs the judges. */
export async function endChat(credentials: Credentials, agent: string, call: string): Promise<void> {
  CallSchema.parse(await dev(credentials, agent, "chat.end", { call }));
}
