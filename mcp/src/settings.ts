/** What the server is told by its environment: where it listens, the address it is reached at, and the gateway whose tools it hosts. */

/** The variables, as an operator sets them. */
export const PORT_VARIABLE = "PINECALL_MCP_PORT";
export const ADDRESS_VARIABLE = "PINECALL_MCP_URL";
/** The gateway's public address — the one the CLI reads too: a link a tool answers points at it, and a person approves there. */
export const GATEWAY_VARIABLE = "PINECALL_URL";

export const DEFAULT_PORT = 8787;
/** The one path the protocol is spoken at. */
export const MCP_PATH = "/mcp";

export interface Settings {
  port: number;
  /** This server's own public address, no path: `https://mcp.example.com`. */
  address: string;
  /** The gateway's public address, no path: the authorization server, and where every tool acts. */
  gateway: string;
}

/** The settings an environment says, or the sentence that names what it lacks. */
export function readSettings(env: NodeJS.ProcessEnv): Settings {
  const [address, gateway] = [addressOf(env, ADDRESS_VARIABLE), addressOf(env, GATEWAY_VARIABLE)];
  const port = Number(env[PORT_VARIABLE] ?? DEFAULT_PORT);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`${PORT_VARIABLE} is ${env[PORT_VARIABLE]}: a port, 1 to 65535`);
  return { port, address, gateway };
}

function addressOf(env: NodeJS.ProcessEnv, variable: string): string {
  const said = env[variable];
  if (said === undefined || said === "") throw new Error(`${variable} is not set: the address, as https://name with no path`);
  let parsed: URL;
  try {
    parsed = new URL(said);
  } catch {
    throw new Error(`${variable} is ${said}: an address, as https://name with no path`);
  }
  if (parsed.pathname !== "/" || parsed.search !== "" || parsed.hash !== "") throw new Error(`${variable} is ${said}: the address alone, with no path`);
  return parsed.origin;
}
