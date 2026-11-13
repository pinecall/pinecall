/** `serve app`: what the project's voice app is, as one line of JSON, for a CLI that never loads it. */

import { parseArgs } from "node:util";

import type { World } from "../client/signed.js";
import type { Io } from "./io.js";
import { CannotServe, loadApp, loadServed } from "./load.js";

/** What `serve app` prints. */
export interface Described {
  name: string;
  /** The app's page: its built folder from the project's root, the slug of the agent a visitor reaches, and the one environment it is served in, when it has one. */
  page: { dir: string; agent: string; only?: World } | null;
}

/** Print the app at `--app`, its classes read from each `--file` served as its `--slug`. */
export async function described(argv: string[], io: Io): Promise<number> {
  const { values } = parseArgs({ args: argv, options: { file: { type: "string", multiple: true }, slug: { type: "string", multiple: true }, app: { type: "string" } } });
  const files = values.file ?? [];
  const slugs = values.slug ?? [];
  if (values.app === undefined || files.length !== slugs.length) throw new CannotServe("serve app takes --app, and one --slug for each --file");
  // Every class is loaded before the app, so the app's file finds the modules it imports already there.
  const classes = new Map<unknown, string>();
  for (const [at, file] of files.entries()) classes.set((await loadServed(file, slugs[at]!)).ctor, slugs[at]!);
  const app = await loadApp(values.app);
  const page = app.paged;
  const agent = page === undefined ? undefined : classes.get(page.answers);
  if (page !== undefined && agent === undefined) throw new CannotServe(`${app.name}'s page reaches ${page.answers.name}, and no agent of the project is that class`);
  const told: Described = { name: app.name, page: page === undefined || agent === undefined ? null : { dir: page.dir, agent, ...(page.only === undefined ? {} : { only: page.only }) } };
  io.out.write(`${JSON.stringify(told)}\n`);
  return 0;
}
