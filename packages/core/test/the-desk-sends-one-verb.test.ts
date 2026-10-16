/** use-supervise.ts Desk with stubbed fetch and LiveKit room: requests sent and mic handling. */

import { beforeEach, expect, test, vi } from "vitest";

// LiveKit is stubbed: checks one seat request, mic via setMicrophoneEnabled, and unpublish on release.
const room = {
  connected: [] as [string, string][],
  microphone: 0,
  unpublished: [] as boolean[],
  disconnected: 0,
};

vi.mock("livekit-client", () => {
  class StubbedRoom {
    localParticipant = {
      setMicrophoneEnabled: (on: boolean): Promise<void> => {
        if (on) room.microphone += 1;
        return Promise.resolve();
      },
      getTrackPublication: (): { track: object } | undefined =>
        room.microphone > room.unpublished.length ? { track: {} } : undefined,
      unpublishTrack: (_track: object, stop: boolean): Promise<void> => {
        room.unpublished.push(stop);
        return Promise.resolve();
      },
    };

    connect(url: string, token: string): Promise<void> {
      room.connected.push([url, token]);
      return Promise.resolve();
    }

    disconnect(): Promise<void> {
      room.disconnected += 1;
      return Promise.resolve();
    }
  }
  return { Room: StubbedRoom, Track: { Source: { Microphone: "microphone" } } };
});

const { Desk } = await import("../src/use-supervise");

const CREDENTIALS = { base: "/", key: "pk_test_a_key_the_desk_signs_with" };
const CALL = "call_9f2a";
// Text threads have no room, so the desk must never request the mic.
const SPOKEN = true;
const A_THREAD = false;

// Requests made and canned responses, in order.
let asked: { url: string; method: string; body: unknown }[] = [];
let answers: { status: number; body: unknown }[] = [];

beforeEach(() => {
  asked = [];
  answers = [];
  room.connected = [];
  room.microphone = 0;
  room.unpublished = [];
  room.disconnected = 0;
  // Door URLs resolve against the page origin (api.ts).
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:53211" } });
  vi.stubGlobal("fetch", (door: URL, sent: { method: string; body: string }) => {
    asked.push({ url: door.toString(), method: sent.method, body: JSON.parse(sent.body) });
    const answer = answers.shift() ?? { status: 202, body: {} };
    return Promise.resolve({
      ok: answer.status < 300,
      status: answer.status,
      statusText: "",
      json: () => Promise.resolve(answer.body),
    });
  });
});

test("a whisper is one post of the wire's own verb to that call's door", async () => {
  await new Desk(CREDENTIALS, CALL, SPOKEN).send({ verb: "whisper", text: "hay un hueco a las 15:40" });
  expect(asked).toEqual([
    {
      url: `http://127.0.0.1:53211/v1/calls/${CALL}/verbs`,
      method: "POST",
      body: { verb: "whisper", text: "hay un hueco a las 15:40" },
    },
  ]);
});

test("the page never sends a verb the wire does not know", async () => {
  const desk = new Desk(CREDENTIALS, CALL, SPOKEN);
  await expect(desk.send({ verb: "shout", text: "!" } as never)).rejects.toThrow();
  expect(asked).toEqual([]);
});

test("a refused verb comes back in the gateway's own words", async () => {
  answers = [{ status: 409, body: { detail: "the call has ended" } }];
  await expect(new Desk(CREDENTIALS, CALL, SPOKEN).send({ verb: "end" })).rejects.toThrow("the call has ended");
});

test("taking the line twice mints one seat and opens the microphone each time", async () => {
  answers = [
    { status: 200, body: { server_url: "ws://127.0.0.1:7880", participant_token: "a-room-token", identity: "sup_a1" } },
    { status: 202, body: {} },
    { status: 202, body: {} },
  ];
  const desk = new Desk(CREDENTIALS, CALL, SPOKEN);
  await desk.take();
  await desk.take();

  expect(asked.map((one) => one.url.split("/").pop())).toEqual(["supervise", "verbs", "verbs"]);
  expect(asked.slice(1).map((one) => one.body)).toEqual([{ verb: "takeover" }, { verb: "takeover" }]);
  expect(room.connected).toEqual([["ws://127.0.0.1:7880", "a-room-token"]]);
  expect(room.microphone).toBe(2);
});

test("handing the line back tells the call first and stops the microphone after", async () => {
  answers = [
    { status: 200, body: { server_url: "ws://127.0.0.1:7880", participant_token: "a-room-token", identity: "sup_a1" } },
    { status: 202, body: {} },
    { status: 202, body: {} },
  ];
  const desk = new Desk(CREDENTIALS, CALL, SPOKEN);
  await desk.take();
  await desk.give();

  expect(asked.at(-1)?.body).toEqual({ verb: "release" });
  expect(room.unpublished).toEqual([true]);
  expect(room.disconnected).toBe(0);
});

test("leaving the screen leaves the room", async () => {
  answers = [
    { status: 200, body: { server_url: "ws://127.0.0.1:7880", participant_token: "a-room-token", identity: "sup_a1" } },
    { status: 202, body: {} },
  ];
  const desk = new Desk(CREDENTIALS, CALL, SPOKEN);
  await desk.take();
  await desk.leave();

  expect(room.unpublished).toEqual([true]);
  expect(room.disconnected).toBe(1);
});

test("a thread's desk takes it with the verb alone: no seat, and no microphone", async () => {
  const desk = new Desk(CREDENTIALS, CALL, A_THREAD);
  await desk.take();

  expect(asked.map((one) => one.url.split("/").pop())).toEqual(["verbs"]);
  expect(asked.map((one) => one.body)).toEqual([{ verb: "takeover" }]);
  expect(room.connected).toEqual([]);
  expect(room.microphone).toBe(0);
});

test("handing a thread back is the verb alone too", async () => {
  const desk = new Desk(CREDENTIALS, CALL, A_THREAD);
  await desk.take();
  await desk.give();

  expect(asked.at(-1)?.body).toEqual({ verb: "release" });
  expect(room.unpublished).toEqual([]);
  expect(room.disconnected).toBe(0);
});
