/** The console's Runs and Personas screens: a call promoted to a candidate, a generated persona kept as a file, the judges' drift, the reproductions a suite wrote. */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import { DevRefused } from "@pinecall/agents/client";
import { z } from "zod";

import * as evals from "../../evals/service/index.js";
import type { Here, Screen } from "./screen.js";

const A_WEEK = 7 * 24 * 60 * 60;
const A_MONTH = 30 * 24 * 60 * 60;
const A_RUN = /^[A-Za-z0-9_-]{1,64}$/;
const A_GOLDEN = /^[^/\\]{1,120}$/;

const Promote = z.object({ call: z.string().min(1), name: z.string().min(1).optional(), from_seq: z.number().int().min(0).default(0) });
// What `PUT …/personas/{name}` takes, with the name: the file is that object, the name its own.
const PersonaWrite = z.object({ name: z.string().min(1), goal: z.string().min(1), style: z.string().min(1) }).passthrough();
const Drift = z.object({
  agent: z.string().min(1),
  window: z.number().min(60).max(A_MONTH * 12).default(A_WEEK),
  baseline: z.number().min(60).max(A_MONTH * 12).default(A_MONTH),
  threshold: z.number().min(0).max(100).default(evals.THRESHOLD),
});
// Shape-checked before a path is joined: a run is an id and a golden a name, never a path.
const Reproduction = z.object({ run: z.string().regex(A_RUN, "a run is an id, not a path"), golden: z.string().regex(A_GOLDEN, "a golden is a name, not a path").optional() });

/** Promote: written to the agent's own `test/candidates`, so it lives here and not in the gateway; a person edits it before it is a golden. */
export function promoteHandlers(here: Here): Screen {
  return {
    verbs: {
      "promote.roster": async () => ({ agent: here.home.name, out: relative(here.home.root, here.home.candidates) }),
      "promote.write": async (asked) => {
        const wanted = Promote.parse(asked);
        const written = await evals.promoteCall(here.ctx, evals.PromoteInput.parse({ call: wanted.call, name: wanted.name, out: here.home.candidates, fromSeq: wanted.from_seq }));
        here.ctx.io.print(`${written.path}  promoted from ${wanted.call}`);
        return written;
      },
    },
  };
}

/** A persona the console generated and kept, for a class that owns its roster: written under the agent's own `test/personas/`, which the class reads. */
export function personaHandlers(here: Here): Screen {
  return {
    verbs: {
      "personas.write": async (asked) => {
        const { name, ...rest } = PersonaWrite.parse(asked);
        const path = await evals.writePersonaFile(here.home.personas, { name, ...(rest as evals.PersonaFile) });
        here.ctx.io.print(`${path}  written from the console`);
        return { path: relative(here.home.root, path), name };
      },
    },
  };
}

/** Drift: computed here, to keep hundreds of round trips out of the browser; nothing is re-judged. */
export function driftHandlers(here: Here): Screen {
  return {
    verbs: {
      "drift.read": async (asked) => {
        const wanted = Drift.parse(asked);
        const drift = await evals.driftOf(here.ctx, evals.DriftInput.parse(wanted));
        return { agent: wanted.agent, window: wanted.window, baseline: wanted.baseline, threshold: wanted.threshold, drift };
      },
    },
  };
}

/** Reproductions: `.pinecall/evals/<run>/<golden>.json`, the full model requests the log keeps only as hashes. */
export function reproductionHandlers(under: string = evals.REPRODUCTIONS): Screen {
  return {
    verbs: {
      "reproductions.roster": async (asked) => {
        const { run } = Reproduction.parse(asked);
        const folder = join(under, run);
        if (!existsSync(folder)) throw new DevRefused(404, `no reproduction of ${run} under ${under}: the suite writes them where it was run, and a run that was green wrote none`);
        const goldens = readdirSync(folder).filter((name) => name.endsWith(".json")).map((name) => name.slice(0, -".json".length)).sort();
        return { run, folder, goldens };
      },
      "reproductions.read": async (asked) => {
        const { run, golden } = Reproduction.parse(asked);
        if (golden === undefined) throw new DevRefused(422, "golden is a name, and it was missing");
        const file = join(under, run, `${golden}.json`);
        if (!existsSync(file)) throw new DevRefused(404, `no reproduction of ${golden} in ${join(under, run)}`);
        return JSON.parse(readFileSync(file, "utf8")) as Record<string, unknown>;
      },
    },
  };
}
