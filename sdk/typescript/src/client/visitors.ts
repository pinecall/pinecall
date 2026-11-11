// A visitor's ticket and a visitor's code, asked of the gateway with the key: what a page's own server answers its page with.

import { signed, type World } from "./signed.js";

/** The gateway and the key a visitor's ticket is minted with. */
export interface VisitorDoor {
  url: string;
  apiKey: string;
  env?: World | undefined;
}

/** What the gateway answered, passed on to the page as it is. */
export interface Answered {
  status: number;
  body: string;
}

async function asked(door: VisitorDoor, path: string, body: Record<string, unknown>): Promise<Answered> {
  const answered = await fetch(`${door.url.replace(/\/+$/, "")}${path}`, {
    method: "POST",
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: answered.status, body: await answered.text() };
}

/** A seat in a new call with `agent`: `POST /v1/tokens`. */
export const visitorTicket = (door: VisitorDoor, agent: string, scope: "talk" | "chat", resume?: string): Promise<Answered> =>
  asked(door, "/v1/tokens", { agent, scope, ...(resume === undefined ? {} : { resume }) });

/** A code a visitor keys when they call `agent`: `POST /v1/codes`. */
export const visitorCode = (door: VisitorDoor, agent: string): Promise<Answered> => asked(door, "/v1/codes", { agent });
