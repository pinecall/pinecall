/** The primitive under every surface: a value, whoever watches it, and ten paints a second. */

/** A value that changes, and a way to hear it change. Every state it hands out is a new object. */
export interface Store<T> {
  readonly state: T;
  /** `fn` hears every new state. Returns the call that stops it hearing. */
  subscribe(fn: (state: T) => void): () => void;
  /** Nobody hears anything again, and nothing is left running. */
  close(): void;
}

// Ten paints a second. Nobody reads faster than that, and a burst of interim transcripts inside
// one turn would repaint the whole window dozens of times while somebody is trying to read it.
export const FRAME_MS = 100;

/** The writer's side of a store. */
export interface Cell<T> extends Store<T> {
  /** Publish now: watchers hear it before this returns. A paint that was waiting rides along. */
  publish(patch: Partial<T>): void;
  /** Publish within FRAME_MS: asked for many times in one frame, watchers hear once, the latest. */
  paint(latest: () => Partial<T>): void;
}

/** A store holding `initial`. A patch that changes nothing is not a new state and is not heard. */
export function cell<T extends object>(initial: T): Cell<T> {
  let state = initial;
  let waiting: (() => Partial<T>) | null = null;
  let frame: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  const watchers = new Set<(state: T) => void>();

  const publish = (patch: Partial<T>): void => {
    if (closed) return;
    const merged = { ...(waiting === null ? {} : waiting()), ...patch };
    waiting = null;
    if (frame !== null) clearTimeout(frame);
    frame = null;
    if (Object.entries(merged).every(([key, value]) => Object.is(Reflect.get(state, key), value))) return;
    state = { ...state, ...merged };
    for (const watcher of [...watchers]) watcher(state);
  };

  return {
    get state() {
      return state;
    },
    subscribe(fn) {
      if (closed) return () => {};
      watchers.add(fn);
      return () => {
        watchers.delete(fn);
      };
    },
    close() {
      closed = true;
      waiting = null;
      if (frame !== null) clearTimeout(frame);
      frame = null;
      watchers.clear();
    },
    publish,
    paint(latest) {
      if (closed) return;
      waiting = latest;
      frame ??= setTimeout(() => publish({}), FRAME_MS);
    },
  };
}
