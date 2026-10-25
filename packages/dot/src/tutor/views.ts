/** What the page draws for the agent's own tools: a card beside the face each time one of them finishes. */
//
// A project's agent has tools of its own: free times, a booking, a piece of code. Their results are
// already on the call's log; the page says, by tool name, how to draw one, and the tutor puts it on a
// card when the tool finishes. A page that joins a call under way shows none of what ran before. The
// visitor answers on the card in words the agent hears (`send`), never by a click the agent did not
// ask for: the card is a way to say it, not a door round the agent.

import type { RoomState, RoomStore } from "@pinecall/room";

import { Card } from "../pointer/card.js";

/** What a view may do. */
export interface ViewTools {
  /** Say something to the agent in writing, as the visitor: a time picked, a name and an email typed. */
  send(text: string): void;
  /** Put the card away. */
  hide(): void;
  /** The call as it is now, for a view that marks what the agent chose. */
  state(): RoomState;
}

/** Draw a tool's result into `host`; answer how to take it down, if there is anything to. */
export type ViewRenderer = (host: HTMLElement, result: unknown, tools: ViewTools) => void | (() => void);

/** The page's views, by the name of the agent's tool. */
export type Views = Record<string, ViewRenderer | undefined>;

export class Screen {
  readonly #call: RoomStore;
  readonly #card: Card;
  readonly #views: () => Views | undefined;
  #on: string | null = null;
  #seen = new Set<string>();

  /** `views` is read each time a tool finishes; `card` is where they are drawn. */
  constructor(call: RoomStore, card: Card, views: () => Views | undefined) {
    this.#call = call;
    this.#card = card;
    this.#views = views;
  }

  /** Follow the call: draw the last finished tool a view names, hide the card when the call is over. */
  update(state: RoomState): void {
    if (state.phase !== "live") {
      this.#on = null;
      this.#card.hide();
      return;
    }
    const finished = state.log.tools.filter((run) => run.status === "done");
    if (state.call !== this.#on) {
      this.#on = state.call;
      this.#seen = new Set(finished.map((run) => run.call_id));
      this.#card.hide();
      return;
    }
    const views = this.#views();
    let latest: { render: ViewRenderer; result: unknown } | null = null;
    for (const run of finished) {
      if (this.#seen.has(run.call_id)) continue;
      this.#seen.add(run.call_id);
      const render = views?.[run.name];
      if (render !== undefined) latest = { render, result: run.output };
    }
    if (latest === null) return;
    const { render, result } = latest;
    const tools: ViewTools = {
      send: (text) => void this.#call.send(text).catch(() => undefined),
      hide: () => this.#card.hide(),
      state: () => this.#call.state,
    };
    this.#card.show((body) => render(body, result, tools));
  }

  close(): void {
    this.#card.close();
  }
}
