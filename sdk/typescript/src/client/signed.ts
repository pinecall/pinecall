// Request headers for the gateway: the API key and the world the request acts in.

/** One of the gateway's two worlds. */
export type World = "sandbox" | "production";

/**
 * Header naming the world the request acts in. A person's key opens both worlds and this picks
 * one (absent, the sandbox); a server token's world is fixed by its prefix, and the header may
 * only agree.
 */
export const ENV_HEADER = "pinecall-env";

/**
 * Headers for one request or socket upgrade: the key as a Bearer (never in a URL, which lands in
 * access logs) and the world if given. An empty key sends no authorization header.
 */
export function signed(apiKey: string, world?: World): Record<string, string> {
  const headers: Record<string, string> = apiKey === "" ? {} : { authorization: `Bearer ${apiKey}` };
  if (world !== undefined) headers[ENV_HEADER] = world;
  return headers;
}
