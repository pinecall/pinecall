// A live call told to take another agent's model and voice: `POST /v1/calls/{call}/stages`.

import { signed, type World } from "./signed.js";

/**
 * Ask the gateway to run a live call on the stages of `agent` from here on. Answers the status:
 * 202 once the call's worker was told, 404 for a call no worker runs (a written one), 409 for one that is over.
 */
export async function stagedAs(door: { url: string; apiKey: string; env?: World | undefined }, call: string, agent: string): Promise<number> {
  const answered = await fetch(`${door.url.replace(/\/+$/, "")}/v1/calls/${encodeURIComponent(call)}/stages`, {
    method: "POST",
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    body: JSON.stringify({ agent }),
  });
  await answered.arrayBuffer();
  return answered.status;
}
