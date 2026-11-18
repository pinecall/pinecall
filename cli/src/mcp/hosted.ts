/** The server as Pinecall hosts it: the tools that need no machine, each call run on the key its request carried. */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { accountsGateway, getWhoami, type Whoami } from "../api/accounts.js";
import { GatewayClient, type Env } from "../api/client.js";
import type { Context } from "../context.js";
import { GatewayError } from "../errors.js";
import { CollectingIO } from "../kit/io.js";
import { serverEnvOf, type Credentials } from "../project/credentials.js";
import type { AgentChoice, AgentHome } from "../project/layout.js";
import { version } from "../version.js";
import { createServer, type Trace } from "./server.js";
import { Session, type Reached } from "./session.js";
import { ToolRefused, type ToolContext } from "./tool.js";
import { STAGES, type Stage } from "./tools/index.js";

export const NO_FOLDER =
  "this reads or writes an agent's files, and Pinecall's hosted server works on no folder: the server on the person's own machine does it (`npm i -g pinecall && pinecall mcp install`), or `pinecall` in a terminal";
export const NAME_THE_AGENT = "name the agent (`agent`): `agent` with action `list` says the ones this org holds now";
export const KEY_SOURCE = "this connection's sign-in";

const UNAUTHORIZED = 401;

/** Every stage's tools that act on no machine: what a hosted server offers. */
export const HOSTED_STAGES: readonly Stage[] = STAGES.map((stage) => ({ ...stage, tools: stage.tools.filter((tool) => !tool.machine) })).filter((stage) => stage.tools.length > 0);

/** The first words of a hosted server's instructions: the same product, with no folder and no process of the person's. */
export const HOSTED_JOURNEY = `Pinecall runs voice and chat agents. This is Pinecall's hosted server: it acts in the org the
person connected, on the agents that org runs, with no folder and no process of the person's.

The journey: \`whoami\` says the org and whether production is allowed → \`agent\` with action \`list\`
names the agents held now, and every tool that acts on one takes that name as \`agent\` → \`chat\` talks
to one, \`simulate\` plays a caller against it, \`test\` plays the org's dataset of cases (\`case\`,
\`dataset\`) → \`calls\` lists what happened and \`call\` reads one call's log whole → \`agent\`,
\`voices\`, \`lexicon\`, \`docs\` and \`memory\` tune an agent (an app written as code, in the sandbox, in
whatever its class does not declare) → \`cases\`, \`judges\`, \`personas\` and \`monitors\` hold its quality →
\`supervise\` watches a live call and moves on it → \`console_url\` opens the console for the person.
\`studio\` is the way to an agent with no code: \`new\` → \`save\` its instructions, tools and data
collection → \`try\` each tool → \`chat\` with it by name → \`deploy\` it.
\`docs_search\` and \`get_doc\` read docs.pinecall.io: read a page whole before writing code from it.

What needs an agent's files is the server on the person's own machine, added with
\`npm i -g pinecall && pinecall mcp install\`: writing its class and holding it while it is written,
its goldens and its documents as files, uploading a project. An action that needs them is refused
here saying so.

Every tool acts in the sandbox, and in production when asked with \`prod: true\`; the org's own
switch still decides whether the person may.

A tool that runs long (\`test\`, \`simulate\`, \`deploy\`) answers within \`wait_s\` seconds (25 unless
asked, at most 50) with what it has, and says how to keep waiting.

The rule is that no key is printed and none is passed through you: no tool takes a vendor key, a
carrier secret or an app's secret, and none returns a Pinecall key. When a step needs one, never ask
for it: give the person the command to type in their own terminal, which reads the secret with
nothing echoed — \`pinecall providers add <vendor>\`, \`pinecall carriers add twilio --account-sid AC… --user SK…\`
(\`sip\`, \`whatsapp\` and \`email\` the same way), \`pinecall secrets set <NAME>\` — and go on once they say it is done.

What cannot be undone is not a tool: erasing data, forgetting a contact, dropping a base, a number
or a carrier, removing a deployed app. Those stay \`pinecall\` verbs a person types.`;

/** What a hosted server keeps for one key between its requests: the written calls open, the runs in flight. */
export class HostedSession extends Session {
  override readonly writesFiles = false;

  constructor(
    /** The gateway's public address: the one a link the tools answer points at. */
    readonly gateway: string,
    readonly key: string,
  ) {
    super({}, async () => []);
  }

  override async project(): Promise<string> {
    throw new ToolRefused(NO_FOLDER);
  }

  override open(): string {
    throw new ToolRefused(NO_FOLDER);
  }

  override async contextFor(prod: boolean): Promise<ToolContext> {
    return new HostedContext(this, prod ? "production" : "sandbox");
  }

  /** The agent is whoever holds the name in the env asked: nothing is held here. */
  override async reach(_ctx: Context, agent: string | undefined): Promise<Reached> {
    if (agent === undefined) throw new ToolRefused(NAME_THE_AGENT);
    return { slug: agent };
  }

  override secrets(): string[] {
    return [this.key];
  }
}

/** A tool call's Context with no folder under it: the key and the gateway are the request's, and a file asked for is refused. */
class HostedContext implements ToolContext {
  readonly io = new CollectingIO();
  readonly signal = new AbortController().signal;
  // Nothing of the server's own environment is a tenant's to read.
  readonly processEnv: NodeJS.ProcessEnv = {};
  #gateway: GatewayClient | undefined;

  constructor(
    readonly session: HostedSession,
    public env: Env,
  ) {}

  get cwd(): string {
    throw new ToolRefused(NO_FOLDER);
  }

  credentials(): Credentials {
    return { url: this.session.gateway, key: this.session.key, source: KEY_SOURCE };
  }

  async prepare(): Promise<void> {
    // The key came with the request: there is none to mint.
  }

  gateway(): GatewayClient {
    if (this.#gateway !== undefined && this.#gateway.env === this.env) return this.#gateway;
    // A person's key opens both envs and the header says which; a server's token has one env.
    const token = serverEnvOf(this.session.key);
    if (token !== undefined && token !== this.env) throw new ToolRefused(`this connection's key is a ${token} server's token: it acts in ${token} alone`);
    this.#gateway = new GatewayClient(this.session.gateway, this.session.key, this.env);
    return this.#gateway;
  }

  agents(): AgentHome[] {
    throw new ToolRefused(NO_FOLDER);
  }

  agent(): AgentHome {
    throw new ToolRefused(NO_FOLDER);
  }

  slug(_verb: string, choice: AgentChoice = {}): string {
    if (choice.agent === undefined) throw new ToolRefused(NAME_THE_AGENT);
    return choice.agent;
  }
}

/** How a hosted server is built: where its trace goes, and what a host is told of every tool. */
export interface HostedOptions {
  trace?: Trace;
  meta?: Record<string, unknown>;
}

/** A server over the hosted tools for one key's session; the transport is whoever hosts it's. */
export function hostedServer(session: HostedSession, options: HostedOptions = {}): McpServer {
  return createServer(version(), {}, { stages: HOSTED_STAGES, session, journey: HOSTED_JOURNEY, hosted: true, ...(options.trace === undefined ? {} : { trace: options.trace }), ...(options.meta === undefined ? {} : { meta: options.meta }) });
}

/** Who a key is at the gateway; null for one that opens nothing there. Any other failure is thrown. */
export async function whoHolds(gateway: string, key: string): Promise<Whoami | null> {
  try {
    return await getWhoami(accountsGateway(gateway, key));
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === UNAUTHORIZED) return null;
    throw failed;
  }
}

export { version };
export type { Trace, Whoami };
