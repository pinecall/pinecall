/** The lines `pinecall start` prints once an agent is registered: connected, its routes, its line. */

/** What the connected line says about one agent. */
export interface Connected {
  slug: string;
  url: string;
  /** How many tools it declares; absent when the gateway would not say. */
  tools?: number | undefined;
  /** The org and env that took it; absent when the gateway does not say. */
  org?: string | undefined;
  env?: string | undefined;
  /** Where the key was read from: the environment or the project's .env. */
  source?: string | undefined;
}

/** A route of the org, as the routes line needs it: which agent, which channel, which number if any. */
export interface RouteOf {
  agent: string;
  channel: string;
  number: string | null;
}

/**
 * The line `pinecall start` prints once registered: slug, org, env, gateway, key source, tools.
 * The org and key source are shown because a shell-exported key overrides the project's and can
 * register the agent into another org.
 */
export function connectedLine(agent: Connected): string {
  const said = [agent.slug];
  if (agent.org !== undefined) said.push(agent.org);
  if (agent.env !== undefined) said.push(agent.env);
  said.push(`connected to ${agent.url}`);
  if (agent.source !== undefined) said.push(`key from ${agent.source}`);
  if (agent.tools !== undefined) said.push(`tools ${agent.tools}`);
  return said.join(" · ");
}

/** The routes line: web (always) plus every phone line the org assigned to this agent. */
export function routesLine(slug: string, routes: readonly RouteOf[]): string {
  const its = routes.filter((one) => one.agent === slug);
  const said = its.map((one) => (one.number === null ? one.channel : `${one.channel} ${one.number}`));
  return `doors    ${["web", ...said].join(" · ")}`;
}

/** The console line: a signed-in link, or the address alone, or why there is none. */
export function talkLine(url: string, signedIn: boolean): string {
  return signedIn ? `talk to it  ${url}   (opens within five minutes, once)` : `talk to it  ${url}`;
}

export function talkUnavailable(why: string): string {
  return `talk to it  not available: ${why}`;
}

export function lineLine(described: string): string {
  return `line     ${described}`;
}

export function lineUnavailable(why: string): string {
  return `line     not available: ${why}`;
}

export function consoleLine(url: string): string {
  return `console  ${url}   (opens within five minutes, once)`;
}

/** The line a reload prints: the version of the class answering now. */
export function reloadedLine(version: number): string {
  return `reloaded · version ${version} answering`;
}

/** The line a save that does not load prints: the version before keeps answering, and the load's own sentence. */
export function notReloadedLine(version: number, why: string): string {
  return `the save does not load, version ${version} keeps answering: ${why}`;
}
