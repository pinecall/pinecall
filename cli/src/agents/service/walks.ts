/** A tutor's walks as its agent published them: listed, and one played on this machine sentence by sentence. */

import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import * as api from "../../api/agents.js";
import type { Context } from "../../context.js";
import { PinecallError } from "../../errors.js";
import type { FilePlayer } from "../../kit/player.js";
import { agentNamed } from "./settings.js";

/** One walk as the list shows it. */
export interface WalkListed {
  name: string;
  title: string;
  sentences: number;
  ms: number;
  voice: string | null;
}

/** A walk played here: how many sentences, and on which player. */
export interface WalkPlayed {
  walk: string;
  sentences: number;
  player: string;
}

/** The walks the agent published in this env, each with its length; none while it published none. */
export async function listWalks(ctx: Context, agent: string | undefined): Promise<{ agent: string; walks: WalkListed[] }> {
  const slug = agentNamed(ctx, agent);
  const walks = await api.getWalks(ctx.gateway(), slug);
  return {
    agent: slug,
    walks: walks.map((walk) => ({ name: walk.name, title: walk.title, sentences: walk.steps.length, ms: walk.steps.reduce((total, step) => total + step.durationMs, 0), voice: walk.voice })),
  };
}

/** One walk, by its name or its title, played here a sentence at a time; `said` hears each sentence as it starts. */
export async function playWalk(ctx: Context, agent: string | undefined, name: string, play: FilePlayer, said: (sentence: string) => void): Promise<WalkPlayed> {
  const slug = agentNamed(ctx, agent);
  const gw = ctx.gateway();
  const walks = await api.getWalks(gw, slug);
  const wanted = name.trim().toLowerCase();
  const walk = walks.find((one) => one.name.toLowerCase() === wanted || one.title.toLowerCase() === wanted);
  if (walk === undefined) {
    const there = walks.length === 0 ? `${slug} published none: start it with macros in its folder` : `there are ${walks.map((one) => one.name).join(", ")}`;
    throw new PinecallError(`no walk ${name}: ${there}`);
  }
  const folder = mkdtempSync(join(tmpdir(), "pinecall-walk-"));
  try {
    let player = "";
    for (const [at, step] of walk.steps.entries()) {
      const file = join(folder, `${at + 1}.mp3`);
      writeFileSync(file, await api.getLineAudio(gw, step.audio));
      said(step.say);
      const played = play(file);
      if ("failed" in played) throw new PinecallError(played.failed);
      player = played.player;
    }
    return { walk: walk.name, sentences: walk.steps.length, player };
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
}
