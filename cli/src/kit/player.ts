/** The audio players a machine might have, the first one on the PATH, and a file played on it: the one place audio is played. */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";

/**
 * A player's arguments for raw 16-bit PCM on stdin (`raw`) and for a file (`file`). `raw` is null
 * for a player that only opens files, such as `afplay`.
 */
export interface Player {
  name: string;
  raw: ((rate: number, channels: number) => string[]) | null;
  file: string[];
}

export const PLAYERS: readonly Player[] = [
  { name: "afplay", raw: null, file: [] },
  {
    name: "ffplay",
    raw: (rate, channels) => ["-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit", "-f", "s16le", "-ar", String(rate), "-ac", String(channels), "-i", "-"],
    file: ["-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit"],
  },
  { name: "play", raw: (rate, channels) => ["-q", "-t", "raw", "-r", String(rate), "-e", "signed", "-b", "16", "-c", String(channels), "-"], file: ["-q"] },
  { name: "aplay", raw: (rate, channels) => ["-q", "-f", "S16_LE", "-r", String(rate), "-c", String(channels), "-"], file: ["-q"] },
  { name: "pw-play", raw: (rate, channels) => ["--format=s16", `--rate=${rate}`, `--channels=${channels}`, "-"], file: [] },
];

/** The first player on the PATH that takes the given input, or null. */
export function playerFor(way: "raw" | "file", env: NodeJS.ProcessEnv = process.env): Player | null {
  return PLAYERS.find((one) => (way === "file" || one.raw !== null) && onPath(one.name, env)) ?? null;
}

/** Whether an executable of this name is on the PATH, without spawning it. */
export function onPath(name: string, env: NodeJS.ProcessEnv = process.env): boolean {
  // An empty PATH segment would resolve to the cwd.
  return (env["PATH"] ?? "").split(delimiter).some((where) => where !== "" && existsSync(join(where, name)));
}

/** What playing a file came to: the player used, or why it failed. */
export type Played = { player: string } | { failed: string };

/** Plays a file; `playFile` on a machine, a stub in a test. */
export type FilePlayer = (file: string) => Played;

/** Play the file on the first player the machine has, waiting for it to end. */
export function playFile(file: string): Played {
  const player = playerFor("file");
  if (player === null) return { failed: "no player on this machine (afplay, ffplay, play, aplay or pw-play)" };
  const ran = spawnSync(player.name, [...player.file, file], { stdio: "ignore" });
  if (ran.error !== undefined) return { failed: `${player.name} could not start (${ran.error.message})` };
  if (ran.status !== 0) return { failed: `${player.name} could not play it (exit ${ran.status ?? "?"})` };
  return { player: player.name };
}
