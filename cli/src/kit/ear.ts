/** A program that joins a LiveKit room, mixes its audio tracks and writes raw PCM to fd 3; spawned by the listening service. */

import { writeSync } from "node:fs";

import { AudioMixer, AudioStream, Room, RoomEvent, TrackKind } from "@livekit/rtc-node";

// Separate process because @livekit/rtc-node logs noisily to stdout and its native threads would
// keep the CLI alive. Contract: argv = rate, channels; stdin = one JSON line
// {server_url, participant_token}; int16 PCM on fd 3 until stdin closes.
const PCM = 3;

/** Read the first stdin line; stdin stays open because its close is the exit signal. */
function readSeat(): Promise<{ server_url: string; participant_token: string }> {
  return new Promise((answer) => {
    let read = "";
    const take = (chunk: Buffer): void => {
      read += chunk.toString();
      const line = read.indexOf("\n");
      if (line === -1) return;
      process.stdin.off("data", take);
      answer(JSON.parse(read.slice(0, line)) as { server_url: string; participant_token: string });
    };
    process.stdin.on("data", take);
  });
}

async function listen(): Promise<void> {
  const [rate, channels] = process.argv.slice(2).map(Number);
  if (rate === undefined || channels === undefined) throw new Error("usage: ear <rate> <channels>");
  const seat = await readSeat();
  const room = new Room();
  const mixer = new AudioMixer(rate, channels);
  // Mix caller and agent tracks into one stream.
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === TrackKind.KIND_AUDIO) mixer.addStream(new AudioStream(track, rate, channels));
  });
  const leaving = new Promise<void>((left) => {
    process.stdin.once("end", () => left());
    process.stdin.once("close", () => left());
    room.on(RoomEvent.Disconnected, () => left());
  });
  await room.connect(seat.server_url, seat.participant_token, { autoSubscribe: true, dynacast: false });
  void leaving.then(async () => {
    await mixer.aclose();
    await room.disconnect();
    process.exit(0);
  });
  for await (const frame of mixer) {
    writeSync(PCM, Buffer.from(frame.data.buffer, frame.data.byteOffset, frame.data.byteLength));
  }
}

listen().catch((failed: unknown) => {
  process.stderr.write(`${failed instanceof Error ? failed.message : String(failed)}\n`);
  process.exit(1);
});
