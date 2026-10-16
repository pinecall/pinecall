/** @pinecall/room/react: a store read the way React reads one, and one room per mounted component. */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { litAt, room, sayingOf, type Lit, type RoomOptions, type RoomState, type RoomStore, type Store } from "../index.js";

/** The store's state, re-rendering when it changes. Any store of this package. */
export function useStore<T>(store: Store<T>): T {
  const subscribe = useCallback((changed: () => void) => store.subscribe(changed), [store]);
  const read = (): T => store.state;
  return useSyncExternalStore(subscribe, read, read);
}

/** What `useRoom` hands a component: the state, and the verbs to change it. */
export type RoomHandle = RoomState & Pick<RoomStore, "start" | "send" | "callMe" | "byPhone" | "leave" | "playSound">;

/**
 * One room for as long as the component is mounted, closed when it unmounts. The options are read
 * when they are used, never when the room was made: a `tokens` written inline, new every render,
 * is the one that runs.
 */
export function useRoom(options: RoomOptions): RoomHandle {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });
  const [store, setStore] = useState(() => room(readingLatest(latest)));
  const open = useRef(true);
  useEffect(() => {
    // StrictMode unmounts and mounts again with the same state: the room the first mount closed
    // is replaced once, rather than handed back closed.
    if (!open.current) {
      open.current = true;
      setStore(room(readingLatest(latest)));
      return;
    }
    return () => {
      open.current = false;
      store.close();
    };
  }, [store]);
  const state = useStore(store);
  const { start, send, callMe, byPhone, leave, playSound } = store;
  return { ...state, start, send, callMe, byPhone, leave, playSound };
}

/**
 * The agent's reply as the voice says it: `lit` has sounded, `coming` has not, or null when nobody
 * is mid-reply. The clock starts when the reply's first word reaches the page and ticks one frame
 * at a time only while a word is still due. Pass `state.entries` of a live room.
 */
export function useKaraoke(entries: RoomState["entries"]): Lit | null {
  const saying = sayingOf(entries);
  const began = useRef<{ speech: string; at: number } | null>(null);
  const [now, setNow] = useState(() => performance.now());

  if (saying === null) began.current = null;
  else if (began.current?.speech !== saying.speech) began.current = { speech: saying.speech, at: performance.now() };

  const split = saying === null || saying.words.length === 0 ? null : litAt(saying, now - (began.current?.at ?? now));
  const waiting = split !== null && split.coming !== "";

  useEffect(() => {
    if (!waiting) return;
    let frame = requestAnimationFrame(function tick() {
      setNow(performance.now());
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [waiting]);

  return split;
}

/** Options whose every field is the one the component rendered last. */
function readingLatest(latest: { readonly current: RoomOptions }): RoomOptions {
  return {
    get tokens() {
      return latest.current.tokens;
    },
    get gateway() {
      return latest.current.gateway;
    },
    get log() {
      return latest.current.log;
    },
    get callMe() {
      return latest.current.callMe;
    },
    get expect() {
      return latest.current.expect;
    },
    get linger() {
      return latest.current.linger;
    },
    get fetch() {
      return latest.current.fetch;
    },
    get livekit() {
      return latest.current.livekit;
    },
    get onSkipped() {
      return latest.current.onSkipped;
    },
  };
}
