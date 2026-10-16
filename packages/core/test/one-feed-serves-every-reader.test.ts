/** feed.ts: every reader of the org's feed shares one stream, opened with the first and closed with the last. */

import { expect, test } from "vitest";

import { sharedFeed, type FeedListener } from "../src/feed";
import type { LogReader } from "../src/stream";

function listener(heard: string[]): FeedListener {
  return { onEntry: (entry) => heard.push(entry.type), onConnection: (now) => heard.push(`@${now}`) };
}

function stream(): { opened: number; closed: number; reader: () => LogReader; open: (reader: LogReader) => () => void } {
  let held: LogReader | undefined;
  const state = {
    opened: 0,
    closed: 0,
    reader: () => held!,
    open(reader: LogReader) {
      state.opened += 1;
      held = reader;
      return () => (state.closed += 1);
    },
  };
  return state;
}

test("two readers share one stream, and it closes with the last of them", () => {
  const one = stream();
  const feed = sharedFeed(one.open);
  const first: string[] = [];
  const second: string[] = [];

  const stopFirst = feed.listen(listener(first));
  one.reader().onConnection("live");
  const stopSecond = feed.listen(listener(second));
  expect(one.opened).toBe(1);
  expect(second).toEqual(["@live"]);

  one.reader().onEntry({ seq: 1, type: "call.ended", data: {} } as never);
  expect(first).toEqual(["@live", "call.ended"]);
  expect(second).toEqual(["@live", "call.ended"]);

  stopFirst();
  expect(one.closed).toBe(0);
  stopSecond();
  expect(one.closed).toBe(1);

  feed.listen(listener([]));
  expect(one.opened).toBe(2);
});
