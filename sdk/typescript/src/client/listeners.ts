// Event listener registry, shared by agents and calls.

import { type Camel, type Event, type EventData, toCamel } from "../wire/codec.js";
import { type EventType } from "../wire/registry.js";

/** An event's data in camelCase. */
export type Payload<K extends EventType> = Camel<EventData<K>>;

/** A camelCase event, discriminated by `type`. */
export type CamelEvent = { [K in EventType]: { type: K; data: Payload<K> } }[EventType];

/** Listener for one event type. */
export type Listener<K extends EventType, Context> = (data: Payload<K>, context: Context) => unknown;

/** Listener for every event. */
export type AnyListener<Context> = (event: CamelEvent, context: Context) => unknown;

type Erased<Context> = (data: never, context: Context) => unknown;

/** Convert a decoded event's data keys to camelCase. */
export function camelEvent(event: Event): CamelEvent {
  return { type: event.type, data: toCamel(event.data) } as CamelEvent;
}

/**
 * The listeners of one agent or call. A throwing listener (sync or async) is reported to `onError`
 * and the others still run.
 */
export class Listeners<Context> {
  readonly #byType = new Map<string, Set<Erased<Context>>>();
  readonly #any = new Set<AnyListener<Context>>();

  constructor(private readonly onError: (error: Error) => void) {}

  /** Listen for one event type. The returned function stops listening. */
  on<K extends EventType>(type: K, listener: Listener<K, Context>): () => void {
    const listeners = this.#byType.get(type) ?? new Set<Erased<Context>>();
    this.#byType.set(type, listeners);
    listeners.add(listener as Erased<Context>);
    return () => {
      listeners.delete(listener as Erased<Context>);
    };
  }

  /** Listen for every event. The returned function stops listening. */
  onAny(listener: AnyListener<Context>): () => void {
    this.#any.add(listener);
    return () => {
      this.#any.delete(listener);
    };
  }

  /** Dispatch to the type's listeners, then to the catch-all ones. */
  emit(event: CamelEvent, context: Context): void {
    for (const listener of this.#byType.get(event.type) ?? []) {
      this.#run(() => (listener as (data: unknown, context: Context) => unknown)(event.data, context));
    }
    for (const listener of this.#any) {
      this.#run(() => listener(event, context));
    }
  }

  #run(listener: () => unknown): void {
    try {
      const running = listener();
      if (running instanceof Promise) {
        running.catch((failed: unknown) => this.onError(asError(failed)));
      }
    } catch (failed) {
      this.onError(asError(failed));
    }
  }
}

/** Coerce any thrown value to an Error. */
export function asError(thrown: unknown): Error {
  return thrown instanceof Error ? thrown : new Error(String(thrown));
}
