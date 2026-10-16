/** `serve start`: hold the agents named, serve their calls, and leave by draining them. */

import { parseArgs } from "node:util";

import { aLostSocket, DevRefused, Pinecall, type World } from "../client/index.js";

import { mount, type Mounted } from "../runtime/connect.js";
import { drainLine, askedToLeave, drainedUnlessSignalledAgain } from "./leaving.js";
import { eventLine, personLine } from "./lines.js";
import { CannotServe, loadServed } from "./load.js";
import type { Io } from "./io.js";
import { viewingFrom } from "./viewing.js";

/** The console's other verbs are answered by the CLI's companion socket, never by the class. */
export const ONLY_THE_VIEW = "this process answers only view.render: the console's other verbs are the CLI's";

const NO_DOOR = "serve start reads PINECALL_URL and PINECALL_KEY from its environment, and one was not set";

const WORLDS: readonly World[] = ["sandbox", "production"];

/** One agent file and the slug it is served as. */
interface Served {
  file: string;
  slug: string;
}

/** Hold every agent named until asked to leave; the exit code is 0 once they drained. */
export async function start(argv: string[], io: Io): Promise<number> {
  const { values } = parseArgs({
    args: argv,
    options: {
      file: { type: "string", multiple: true },
      slug: { type: "string", multiple: true },
      console: { type: "boolean", default: false },
      events: { type: "boolean", default: false },
    },
  });
  const served = paired(values.file ?? [], values.slug ?? []);
  const pc = clientFrom(io.env);
  for (const one of served) await held(pc, one, values.console === true);
  said(pc, io, values.events === true);
  try {
    await pc.connect();
    if ((await askedToLeave(pc, io)) !== "stopped") {
      const drained = await drainedUnlessSignalledAgain(pc, io);
      if (drained !== undefined) io.err.write(`${drainLine(drained)}\n`);
    }
    return 0;
  } finally {
    pc.close();
  }
}

/** Every `--file` with the `--slug` at its place. */
function paired(files: string[], slugs: string[]): Served[] {
  if (files.length === 0 || files.length !== slugs.length) {
    throw new CannotServe("serve start takes one --slug for each --file, and at least one of each");
  }
  return files.map((file, at) => ({ file, slug: slugs[at]! }));
}

function clientFrom(env: Io["env"]): Pinecall {
  const url = env["PINECALL_URL"];
  const apiKey = env["PINECALL_KEY"];
  if (url === undefined || url === "" || apiKey === undefined || apiKey === "") throw new CannotServe(NO_DOOR);
  const world = env["PINECALL_ENV"];
  if (world === undefined || world === "") return new Pinecall({ url, apiKey });
  if (!WORLDS.includes(world as World)) throw new CannotServe(`PINECALL_ENV is sandbox or production, not ${world}`);
  return new Pinecall({ url, apiKey, env: world as World });
}

// A console's own process takes only the calls that name it; the class draws the panel.
async function held(pc: Pinecall, one: Served, console: boolean): Promise<Mounted> {
  const loaded = await loadServed(one.file, one.slug);
  const mounted = mount(loaded.ctor, { pc, source: loaded.source, file: loaded.file, slug: one.slug, takesUnclaimed: !console });
  const viewing = viewingFrom(loaded.ctor, one.slug);
  mounted.agent.onDev(async (verb, data) => {
    if (verb !== "view.render") throw new DevRefused(404, ONLY_THE_VIEW);
    return { ...(await viewing.render(data)) };
  });
  return mounted;
}

// Listening starts before connect, so agent.registered is the first line. A lost gateway is one
// line per outage, on err so --events stays the wire alone.
function said(pc: Pinecall, io: Io, events: boolean): void {
  pc.onEntries((entry) => {
    const line = events ? eventLine(entry) : personLine(entry);
    if (line !== null) io.out.write(`${line}\n`);
  });
  let lost = false;
  pc.onErrors((failed) => {
    if (!aLostSocket(failed)) return void io.err.write(`${failed.stack ?? failed.message}\n`);
    if (!lost) io.err.write(`gateway  ${failed.message} — reconnecting\n`);
    lost = true;
  });
  pc.onConnected(() => {
    if (lost) io.err.write("gateway  back\n");
    lost = false;
  });
}
