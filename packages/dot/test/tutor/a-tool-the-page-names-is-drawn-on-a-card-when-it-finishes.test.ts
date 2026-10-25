// A tool the page names a view for is drawn on a card beside the face when it finishes; what ran before the page joined is not.

import type { RoomState, RoomStore } from "@pinecall/room";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Card } from "../../src/pointer/card.js";
import { Screen, type Views } from "../../src/tutor/views.js";
import { aRoom } from "../a-room.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  vi.useRealTimers();
});

type Run = RoomState["log"]["tools"][number];

const run = (id: string, name: string, output: unknown, status = "done"): Run =>
  ({ call_id: id, name, arguments: {}, output, status, speech_id: "s1", error: null }) as unknown as Run;

function live(call: string, tools: Run[]): RoomState {
  const { state } = aRoom();
  return { ...state, phase: "live", call, log: { ...state.log, tools } } as RoomState;
}

function aScreen(views: Views, sent: string[] = []): { screen: Screen; card: Card } {
  const store = { state: live("c1", []), send: async (text: string) => void sent.push(text) } as unknown as RoomStore;
  const card = new Card(document, (part) => document.body.append(part), "Close");
  return { screen: new Screen(store, card, () => views), card };
}

describe("the card of a tool's view", () => {
  it("draws the last tool that finished and has a view, once, and says what the visitor sends", () => {
    const sent: string[] = [];
    const drawn: unknown[] = [];
    const { screen, card } = aScreen(
      {
        freeSlots: (host, result, tools) => {
          drawn.push(result);
          host.innerHTML = `<button>10:00</button>`;
          host.querySelector("button")?.addEventListener("click", () => tools.send("10:00"));
        },
      },
      sent,
    );
    screen.update(live("c1", []));

    screen.update(live("c1", [run("a", "lookUp", "x"), run("b", "freeSlots", { times: ["10:00"] })]));
    screen.update(live("c1", [run("a", "lookUp", "x"), run("b", "freeSlots", { times: ["10:00"] })]));
    document.querySelector<HTMLButtonElement>(".pc-card button:not(.pc-card-x)")?.click();

    expect(drawn).toEqual([{ times: ["10:00"] }]);
    expect(card.shown).toBe(true);
    expect(sent).toEqual(["10:00"]);
  });

  it("draws nothing for a tool still running, one without a view, or one that ran before the page joined", () => {
    const drawn: string[] = [];
    const { screen, card } = aScreen({ freeSlots: (_host, _result) => void drawn.push("slots") });

    screen.update(live("c1", [run("old", "freeSlots", {})]));
    expect(card.shown).toBe(false);
    screen.update(live("c1", [run("old", "freeSlots", {}), run("new", "freeSlots", {}, "running"), run("other", "book", {})]));

    expect(drawn).toEqual([]);
    expect(card.shown).toBe(false);
  });

  it("puts the card away when the call ends, and takes down what it held once it has faded", () => {
    vi.useFakeTimers();
    const takenDown: string[] = [];
    const { screen, card } = aScreen({ freeSlots: () => () => void takenDown.push("down") });
    screen.update(live("c1", []));
    screen.update(live("c1", [run("a", "freeSlots", {})]));
    expect(card.shown).toBe(true);

    screen.update({ ...live("c1", []), phase: "ended" } as RoomState);
    expect(card.shown).toBe(false);
    vi.advanceTimersByTime(300);

    expect(takenDown).toEqual(["down"]);
  });

  it("is put away by its close button", () => {
    const { screen, card } = aScreen({ freeSlots: (host) => void (host.textContent = "times") });
    screen.update(live("c1", []));
    screen.update(live("c1", [run("a", "freeSlots", {})]));

    document.querySelector<HTMLButtonElement>(".pc-card-x")?.click();

    expect(card.shown).toBe(false);
  });
});
