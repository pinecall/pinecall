/** A seat taken on a fake LiveKit, with a sink that records and everything the seat said written down. */

import { joinSeat, type Seat, type Speaking } from "../../src/seat/join.js";
import type { Sink } from "../../src/seat/sink.js";
import { FakeLivekit } from "../a-fake-livekit.js";

/** A sink that keeps what it was handed instead of playing it. */
export class RecordingSink implements Sink {
  playing: HTMLMediaElement[] = [];
  closed = 0;

  add(element: HTMLMediaElement): void {
    this.playing.push(element);
  }

  remove(element: HTMLMediaElement): void {
    this.playing = this.playing.filter((one) => one !== element);
  }

  close(): void {
    this.closed += 1;
    this.playing = [];
  }
}

export interface Taken {
  seat: Seat;
  livekit: FakeLivekit;
  sink: RecordingSink;
  disconnected: number;
  speaking: Speaking[];
  wantsSound: boolean[];
}

export async function take(mode: "talk" | "chat", livekit = new FakeLivekit()): Promise<Taken> {
  const sink = new RecordingSink();
  const speaking: Speaking[] = [];
  const wantsSound: boolean[] = [];
  let disconnected = 0;
  const seat = await joinSeat({
    livekit: livekit.module,
    server_url: "wss://lk.example",
    participant_token: "ticket",
    mode,
    sink,
    on: {
      disconnected: () => {
        disconnected += 1;
      },
      speaking: (now) => speaking.push(now),
      wantsSound: (wanted) => wantsSound.push(wanted),
    },
  });
  return {
    seat,
    livekit,
    sink,
    get disconnected() {
      return disconnected;
    },
    speaking,
    wantsSound,
  };
}
