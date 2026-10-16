/** Where the gateway's doors are, for every API URL the page builds: its own origin's root. */

// The API is at the origin's root whichever world the page is — `/v1/...` is never under
// `/sandbox` — so this is `"/"`, resolved against the page's own origin (core's `api.ts:gatewayUrl`).
// The ROUTER's base is the world's (`lib/mode.ts:WORLD_BASE`), another string on the sandbox's page.
export const API_BASE = "/";
