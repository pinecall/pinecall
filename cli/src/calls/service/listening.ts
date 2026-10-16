/** `--listen`: a live call played on this machine's speakers, through a hidden seat in its room. */

import { spawn, type ChildProcess } from "node:child_process";
import { extname } from "node:path";
import type { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

import * as api from "../../api/calls.js";
import type { Context } from "../../context.js";
import { PinecallError } from "../../errors.js";
import { playerFor, PLAYERS } from "../../kit/player.js";
import { loaderFor } from "../../project/language.js";

/** A listener attached to one call. */
export interface Ear {
  /** This terminal's participant identity. */
  identity: string;
  /** The player's program, for the line that says so. */
  player: string;
  leave(): Promise<void>;
}

// Rooms carry 48 kHz mono (the runtime's speech); ear and player must agree.
const SAMPLE_RATE = 48_000;
const CHANNELS = 1;
// A simulation asks before its room has opened: the call's log says when it has.
const A_ROOM_OPENS_WITHIN_MS = 30_000;
// Grace period before the ear process is killed.
const LEAVING_TAKES_MS = 2_000;
// PCM goes over fd 3: the room library's logger writes to stdout and cannot be silenced.
const PCM = 3;
const ROOM_OPENED = "room.opened";
const CALL_ENDED = "call.ended";

export const NO_PLAYER = `no player on this machine: --listen writes ${SAMPLE_RATE} Hz mono to one of ${PLAYERS.filter((one) => one.raw !== null).map((one) => one.name).join(", ")} — install ffmpeg, sox or alsa-utils`;
export const NO_ROOM_LIBRARY = "--listen joins the call's room from this terminal and needs @livekit/rtc-node, which is an optional dependency: install it (pnpm add @livekit/rtc-node) and listen again";

// `ear.ts` in a checkout, `ear.js` in dist: follows this module's own extension.
const EAR = fileURLToPath(new URL(`../../kit/ear${extname(fileURLToPath(import.meta.url))}`, import.meta.url));

/**
 * Join a live call as a hidden, silent listener and play both tracks locally. The room is joined in
 * a child process (`kit/ear`) because the native room library logs to stdout and keeps threads
 * alive after the call.
 */
export async function listenTo(ctx: Context, call: string): Promise<Ear> {
  const player = startPlayer(ctx.processEnv);
  if (player === null) throw new PinecallError(NO_PLAYER);
  requireRoomLibrary();
  await roomOpened(ctx, call);
  const seat = await api.createListenSeat(ctx.gateway(), call);
  const ear = spawn(process.execPath, [...loaderFor(EAR), EAR, String(SAMPLE_RATE), String(CHANNELS)], { stdio: ["pipe", "ignore", "ignore", "pipe"] });
  (ear.stdio[PCM] as Readable).pipe(player.stdin!);
  ear.stdin!.write(`${JSON.stringify({ server_url: seat.server_url, participant_token: seat.participant_token })}\n`);
  return {
    identity: seat.identity,
    player: player.spawnfile,
    async leave(): Promise<void> {
      // Closing stdin asks the ear to leave; `gone` kills it after a grace period.
      ear.stdin!.end();
      await gone(ear);
      player.stdin!.end();
    },
  };
}

// The stream's own markers (`log.caught_up`) come whatever types are asked for.
async function roomOpened(ctx: Context, call: string): Promise<void> {
  const stop = new AbortController();
  const deadline = setTimeout(() => stop.abort(), A_ROOM_OPENS_WITHIN_MS);
  try {
    for await (const entry of api.followEntries(ctx.gateway(), { call }, { types: [ROOM_OPENED, CALL_ENDED], signal: stop.signal })) {
      if (entry.type === ROOM_OPENED) return;
      if (entry.type === CALL_ENDED) throw new PinecallError(`${call} ended before its room opened`);
    }
  } finally {
    clearTimeout(deadline);
    stop.abort();
  }
  throw new PinecallError(`${call}: its room did not open within ${A_ROOM_OPENS_WITHIN_MS / 1000} s`);
}

/** Throw if `@livekit/rtc-node` is not resolvable, without loading it. */
function requireRoomLibrary(): void {
  try {
    import.meta.resolve("@livekit/rtc-node");
  } catch {
    throw new PinecallError(NO_ROOM_LIBRARY);
  }
}

function gone(ear: ChildProcess): Promise<void> {
  return new Promise((left) => {
    const kill = setTimeout(() => ear.kill("SIGKILL"), LEAVING_TAKES_MS);
    ear.once("exit", () => {
      clearTimeout(kill);
      left();
    });
  });
}

/** Start the first raw-PCM player on PATH, or null when none is installed. */
function startPlayer(env: NodeJS.ProcessEnv): ChildProcess | null {
  const player = playerFor("raw", env);
  if (player === null || player.raw === null) return null;
  return spawn(player.name, player.raw(SAMPLE_RATE, CHANNELS), { stdio: ["pipe", "ignore", "ignore"] });
}
