/** Goldens doors: list the agent directory's goldens and run a chosen set. */

import { z } from "zod";

import type { Credentials } from "@pinecall/core/api";
import { ExpectSchema, TurnSchema } from "@pinecall/core/wire/rest-goldens";
import { dev } from "../../lib/dev";

/** A golden as the companion lists it: its turns whole (none in a file written before turns), and what holds at the end. */
const ListedSchema = z.object({
  name: z.string(),
  turns: z.array(TurnSchema).optional(),
  expect: ExpectSchema,
});
export type Listed = z.infer<typeof ListedSchema>;

/** The class in the running directory, and its goldens. */
const RosterSchema = z.object({ agent: z.string().nullable(), goldens: z.array(ListedSchema) });
export type Roster = z.infer<typeof RosterSchema>;

const StartedSchema = z.object({ run: z.string() });

export interface Wanted {
  agent: string;
  goldens: string[];
  /** `vendor/model` per matrix column; empty uses the configured model. */
  models?: string[];
  voice: boolean;
  background_noise?: number;
  /** 0 to 1. */
  packet_loss?: number;
}

export async function readGoldens(credentials: Credentials, agent: string): Promise<Roster> {
  return RosterSchema.parse(await dev(credentials, agent, "goldens.roster"));
}

/** Start a run of the chosen goldens; resolves to the run id. */
export async function startSuite(credentials: Credentials, wanted: Wanted): Promise<string> {
  return StartedSchema.parse(await dev(credentials, wanted.agent, "goldens.run", wanted)).run;
}
