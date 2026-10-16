// Gateway endpoint URLs, built from the base URL the app configures.

/** `WS /v1/apps`. An http(s) base maps to ws(s). */
export function appsUrl(base: string): string {
  return doorAt(base, "/v1/apps", true);
}

/** `GET /v1/calls/{id}/events`: one call's log, as a JSON page or SSE. */
export function callLogUrl(base: string, call: string): string {
  return doorAt(base, `/v1/calls/${encodeURIComponent(call)}/events`, false);
}

/** `GET /v1/agents/{slug}/calls`: the agent's own log (registrations, configurations, errors). */
export function agentLogUrl(base: string, agent: string): string {
  return doorAt(base, `/v1/agents/${encodeURIComponent(agent)}/calls`, false);
}

/** `GET /v1/events`: the org's feed in the key's world — calls changing, runs, releases — as SSE. */
export function feedUrl(base: string): string {
  return doorAt(base, "/v1/events", false);
}

/** `POST /v1/calls/{id}/lookup`: a knowledge-base search run by the gateway for this call. */
export function lookupUrl(base: string, call: string): string {
  return doorAt(base, `/v1/calls/${encodeURIComponent(call)}/lookup`, false);
}

function doorAt(base: string, path: string, websocket: boolean): string {
  const url = new URL(base);
  const secure = url.protocol === "https:" || url.protocol === "wss:";
  url.protocol = websocket ? (secure ? "wss:" : "ws:") : secure ? "https:" : "http:";
  url.pathname = `${url.pathname.replace(/\/$/, "")}${path}`;
  return url.toString();
}
