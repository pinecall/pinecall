/** The console's Tests and Simulations screens: goldens and personas played through the agent this process serves. */

import { DevRefused } from "@pinecall/agents/client";
import { z } from "zod";

import { chatLine } from "../../calls/render.js";
import { errorMessage } from "../../errors.js";
import * as render from "../../evals/render/index.js";
import * as evals from "../../evals/service/index.js";
import { mine, type Here, type Screen } from "./screen.js";

const RunGoldens = z.object({
  agent: z.string().min(1),
  goldens: z.array(z.string().min(1)).min(1),
  models: z.array(z.string().min(1)).default([]),
  voice: z.boolean().default(false),
  background_noise: z.number().min(0).max(120).optional(),
  packet_loss: z.number().min(0).max(1).optional(),
});

const StartSimulation = z.object({
  agent: z.string().min(1),
  persona: z.string().min(1),
  voice: z.boolean().default(false),
  judge: z.boolean().default(false),
  turns: z.number().int().min(1).max(30).default(evals.TURNS),
  background_noise: z.number().min(0).max(120).optional(),
  /** A percent on the screen; the wire carries a share. */
  packet_loss: z.number().min(0).max(100).optional(),
});

/** Tests: the goldens of this directory listed, and a run of the chosen ones answered with its id once the gateway has it. */
export function goldenHandlers(here: Here): Screen {
  return {
    verbs: {
      "goldens.roster": async () => ({
        agent: here.home.name,
        goldens: (await evals.goldensInFolder(here.home.goldens)).map(({ name, turns, expect }) => ({ name, turns, expect: { ...(expect ?? {}) } })),
      }),
      "goldens.run": async (asked) => {
        const wanted = RunGoldens.parse(asked);
        mine(here, wanted.agent, "run the goldens of");
        if (!wanted.voice && (wanted.background_noise !== undefined || wanted.packet_loss !== undefined)) throw new DevRefused(422, "background noise and packet loss are about audio: a spoken run");
        const chosen = (await evals.goldensInFolder(here.home.goldens)).filter((golden) => wanted.goldens.includes(golden.name));
        const missing = wanted.goldens.filter((name) => !chosen.some((golden) => golden.name === name));
        if (missing.length > 0) throw new DevRefused(404, `no golden called ${missing.join(", ")}`);
        const input = evals.SuiteInput.parse({ voice: wanted.voice, backgroundNoise: wanted.background_noise, packetLoss: wanted.packet_loss, models: wanted.models });
        // The report prints here as `pinecall test` does; the page reads the run from the gateway.
        return await new Promise<{ run: string }>((answer, refuse) => {
          let told = false;
          evals
            .runSuite(here.ctx, here.home.name, chosen, input, here.served.app(), {
              onStarted: (id) => {
                if (!told) answer({ run: id });
                told = true;
              },
            })
            .then(
              (report) => {
                for (const line of render.suite(report, evals.DECLARED_AS)) here.ctx.io.print(line);
                if (!told) refuse(new DevRefused(502, "the suite ended before the gateway opened a run"));
              },
              (failed: unknown) => {
                here.ctx.io.print(`suite failed: ${errorMessage(failed)}`);
                if (!told) refuse(failed);
              },
            );
        });
      },
    },
  };
}

/** Simulations: one persona played against the agent, answered with the call's id as soon as it exists. */
export function simulateHandlers(here: Here): Screen {
  return {
    verbs: {
      "simulate.start": async (asked) => {
        const wanted = StartSimulation.parse(asked);
        mine(here, wanted.agent, "simulate");
        const persona = await evals.getPersona(here.ctx, here.home.name, wanted.persona);
        const input = evals.SimulateInput.parse({
          persona: persona.name,
          judge: wanted.judge,
          voice: wanted.voice,
          turns: wanted.turns,
          backgroundNoise: wanted.background_noise,
          packetLoss: wanted.packet_loss === undefined ? undefined : wanted.packet_loss / 100,
        });
        // Turns print here as `pinecall simulate` does; the simulation keeps running after the answer.
        return await new Promise<{ call: string }>((answer, refuse) => {
          let told = false;
          evals
            .simulate(here.ctx, { slug: here.home.name, app: () => here.served.app() }, persona, input, {
              onOpened: (call) => {
                if (!told) answer({ call });
                told = true;
              },
              onEntry: (entry) => {
                const line = chatLine(entry);
                if (line !== null) here.ctx.io.print(line);
              },
            })
            .then(
              () => {
                if (!told) refuse(new DevRefused(502, "the simulation ended before a call opened"));
              },
              (failed: unknown) => {
                here.ctx.io.print(`simulation failed: ${errorMessage(failed)}`);
                if (!told) refuse(new DevRefused(502, errorMessage(failed)));
              },
            );
        });
      },
    },
  };
}
