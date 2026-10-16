/** The MCP server: every tool registered on one stdio connection, each answer scrubbed, each failure one sentence. */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { fileURLToPath } from "node:url";
import { ZodError } from "zod";

import { errorMessage } from "../errors.js";
import type { IO } from "../kit/io.js";
import { instructions } from "./instructions.js";
import { scrub } from "./scrub.js";
import { Session } from "./session.js";
import type { Tool } from "./tool.js";
import { STAGES, type Stage } from "./tools/index.js";

/** The text content a tool answers with. */
interface Answer {
  [key: string]: unknown;
  content: { type: "text"; text: string }[];
  isError?: boolean;
}

/** One line per call, for the host's log: the tool, how long, how it ended — never its arguments or its answer. */
export type Trace = (line: string) => void;

/** How a server is built: its stages of tools, a session of its own, and where its trace goes. */
export interface ServerOptions {
  stages?: readonly Stage[];
  session?: Session;
  trace?: Trace;
}

/** A server over these tools, one session for its life. */
export function createServer(version: string, processEnv: NodeJS.ProcessEnv, options: ServerOptions = {}): McpServer {
  const stages = options.stages ?? STAGES;
  const server = new McpServer({ name: "pinecall", version }, { instructions: instructions(stages) });
  const session = options.session ?? new Session(processEnv, () => declaredRoots(server));
  const trace = options.trace ?? (() => undefined);
  for (const one of stages.flatMap((stage) => stage.tools)) {
    // The manual rides the description: the one place a host shows the model what a tool is for.
    server.registerTool(one.name, { description: `${one.description}\n\n${one.manual}`, inputSchema: one.schema }, async (args: unknown) => await answered(session, one, args, trace));
  }
  return server;
}

/** Serve on this process's stdin and stdout until the host closes them: stdout is the protocol, and nothing else writes to it. */
export async function serve(version: string, processEnv: NodeJS.ProcessEnv, io: IO, transport: Transport = onStdio()): Promise<void> {
  const session = new Session(processEnv, () => declaredRoots(server));
  const server = createServer(version, processEnv, { session, trace: (line) => io.info(line) });
  const closed = new Promise<void>((ended) => (server.server.onclose = ended));
  await server.connect(transport);
  await closed;
  // A host that hangs up leaves no call open and no agent registered.
  await session.close();
}

// The SDK's stdio transport never notices its input ending: the host hanging up closes it here.
function onStdio(): Transport {
  const transport = new StdioServerTransport();
  process.stdin.once("end", () => void transport.close());
  return transport;
}

// A refusal is the model's to act on: its sentence, scrubbed, and never a stack.
async function answered(session: Session, tool: Tool, args: unknown, trace: Trace): Promise<Answer> {
  const started = Date.now();
  try {
    const ctx = await session.contextFor((args as { prod?: unknown } | undefined)?.prod === true);
    const result = await tool.call(args, ctx);
    trace(`pinecall-mcp · ${tool.name} · ${Date.now() - started} ms · ok`);
    return { content: [{ type: "text", text: scrub(JSON.stringify(result, null, 2), session.secrets(), tool.reveals?.(result) ?? []) }] };
  } catch (failed) {
    const said = failed instanceof ZodError ? failed.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ") : errorMessage(failed);
    trace(`pinecall-mcp · ${tool.name} · ${Date.now() - started} ms · refused`);
    return { content: [{ type: "text", text: scrub(said, session.secrets()) }], isError: true };
  }
}

// A host that declares roots says where the project is; one that does not leaves the cwd and `project open`.
async function declaredRoots(server: McpServer): Promise<string[]> {
  if (server.server.getClientCapabilities()?.roots === undefined) return [];
  try {
    const { roots } = await server.server.listRoots();
    return roots.filter((root) => root.uri.startsWith("file://")).map((root) => fileURLToPath(root.uri));
  } catch {
    return [];
  }
}
