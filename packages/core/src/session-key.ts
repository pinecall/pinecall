/** Persist the person's API key in app-provided storage. */

// Async because the phone's secure store is.
/** String storage supplied by the app: localStorage in the browser, secure store on the phone. */
export interface KeyStorage {
  read(name: string): Promise<string | null>;
  write(name: string, value: string): Promise<void>;
  erase(name: string): Promise<void>;
}

/** The person's key across visits. */
export interface SessionKey {
  /** The stored key, or null. */
  kept(): Promise<string | null>;
  /** Store a key. */
  keep(key: string): Promise<void>;
  /** Remove the stored key. */
  forget(): Promise<void>;
}

// One key per person, not per world: the world is sent on each request.
const KEPT_UNDER = "pinecall.key";

/** A SessionKey backed by the given storage. */
export function sessionKeyIn(storage: KeyStorage): SessionKey {
  return {
    kept: () => storage.read(KEPT_UNDER),
    keep: (key) => storage.write(KEPT_UNDER, key),
    forget: () => storage.erase(KEPT_UNDER),
  };
}
