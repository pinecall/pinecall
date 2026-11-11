/** `serve start`: hold the agents named, serve their calls, and leave by draining them. */

import { parseArgs } from "node:util";

import { aLostSocket, DevRefused, Pinecall, type World } from "../client/index.js";

import type { VoiceApp } from "../runtime/app.js";
import { mount, type Mounted } from "../runtime/connect.js";
import { drainLine, askedToLeave, drainedUnlessSignalledAgain } from "./leaving.js";
import { eventLine, personLine } from "./lines.js";
import { Masking } from "./masking.js";
import { CannotServe, loadApp, loadServed, type Loaded } from "./load.js";
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
      app: { type: "string" },
      console: { type: "boolean", default: false },
      events: { type: "boolean", default: false },
    },
  });
  const served = paired(values.file ?? [], values.slug ?? []);
  const pc = clientFrom(io.env);
  const masking = new Map<string, Masking>();
  // Every class is loaded before the app, so the app's file finds the modules it imports already there.
  const loaded: Loaded[] = [];
  for (const one of served) loaded.push(await loadServed(one.file, one.slug));
  const app = values.app === undefined ? undefined : appOf(await loadApp(values.app), served, loaded);
  const slugs = new Map(loaded.map((one, at) => [one.ctor, served[at]!.slug]));
  served.forEach((one, at) => masking.set(one.slug, new Masking(held(pc, one, loaded[at]!, app, slugs, values.console === true, io).options)));
  said(pc, io, values.events === true, masking);
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

// PINECALL_HOST is the name a hosted app's runner gave it: the gateway knows the release by it.
function clientFrom(env: Io["env"]): Pinecall {
  const url = env["PINECALL_URL"];
  const apiKey = env["PINECALL_KEY"];
  if (url === undefined || url === "" || apiKey === undefined || apiKey === "") throw new CannotServe(NO_DOOR);
  const host = env["PINECALL_HOST"] || undefined;
  const world = env["PINECALL_ENV"];
  if (world === undefined || world === "") return new Pinecall({ url, apiKey, ...(host === undefined ? {} : { host }) });
  if (!WORLDS.includes(world as World)) throw new CannotServe(`PINECALL_ENV is sandbox or production, not ${world}`);
  return new Pinecall({ url, apiKey, env: world as World, ...(host === undefined ? {} : { host }) });
}

// A console's own process takes only the calls that name it; the class draws the panel.
function held(pc: Pinecall, one: Served, loaded: Loaded, app: VoiceApp | undefined, slugs: Map<Loaded["ctor"], string>, console: boolean, io: Io): Mounted {
  const report = (line: string): void => void io.err.write(`${one.slug}  ${line}\n`);
  const declares = app?.declares(loaded.ctor) ?? {};
  const mates = app?.teamOf(loaded.ctor) ?? [];
  const chooses = app?.choosing(loaded.ctor);
  const team = mates.length === 0 ? undefined : new Map(mates.map((mate) => [mate, slugs.get(mate)!]));
  const mounted = mount(loaded.ctor, { pc, source: loaded.source, file: loaded.file, slug: one.slug, takesUnclaimed: !console, report, declares, rules: app?.agents().includes(loaded.ctor) ? app.rules : [], ...(team === undefined ? {} : { team }), ...(chooses === undefined ? {} : { answers: chooses }) });
  if (app !== undefined) pointed(mounted, app.numbersOf(loaded.ctor), report);
  const viewing = viewingFrom(loaded.ctor, one.slug);
  mounted.agent.onDev(async (verb, data) => {
    if (verb !== "view.render") throw new DevRefused(404, ONLY_THE_VIEW);
    return { ...(await viewing.render(data)) };
  });
  return mounted;
}

// An app names classes, and a process serves files: every class the app names is one of the files served.
function appOf(app: VoiceApp, served: Served[], loaded: Loaded[]): VoiceApp {
  for (const ctor of app.agents()) {
    if (loaded.some((one) => one.ctor === ctor)) continue;
    const files = served.map((one) => one.slug).join(", ");
    throw new CannotServe(`${app.name} answers a line with ${ctor.name}, and no agent served here is that class (${files}): it is the default export of its agents/<name>/agent file`);
  }
  return app;
}

// A number is the org's row: the app says who answers it, and the gateway says whether it is so. Said once.
function pointed(mounted: Mounted, numbers: string[], report: (line: string) => void): void {
  const told = new Set<string>();
  mounted.agent.on("agent.registered", (registered) => {
    const answered = new Set(registered.routes.map((route) => route.number));
    for (const number of numbers) {
      if (answered.has(number) || told.has(number)) continue;
      told.add(number);
      report(`${number} is not pointed at this agent yet: \`pinecall numbers\` shows where it rings`);
    }
  });
}

// Listening starts before connect, so agent.registered is the first line. A lost gateway is one
// line per outage, on err so --events stays the wire alone.
function said(pc: Pinecall, io: Io, events: boolean, masking: Map<string, Masking>): void {
  pc.onEntries((entry) => {
    // What it prints is what the call's log keeps: a value the agent declared private never reaches a terminal.
    const shown = masking.get(entry.agent)?.entry(entry) ?? entry;
    const line = events ? eventLine(shown) : personLine(shown);
    if (line !== null) io.out.write(`${line}\n`);
  });
  // A kill travels on the wire as the `error` entry it is (`eventLine`), which the CLI says once; a person's
  // own lines (`personLine`) say it too. Nothing more on err, or the CLI's reader would see it twice.
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
