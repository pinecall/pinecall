/** Browser storage for the session key and tab state; the only module that touches storage. */

import { sessionKeyIn, type KeyStorage } from "@pinecall/core/session-key";

// localStorage, not sessionStorage: login codes are single-use, so a per-tab key would leave new
// tabs signed out. Enforced by test/pages/the-key-is-never-in-the-page.test.ts.
// Writes are synchronous so the key is stored before a following reload or `location.assign`.
const THIS_BROWSER: KeyStorage = {
  read: async (name) => window.localStorage.getItem(name),
  write: async (name, value) => window.localStorage.setItem(name, value),
  erase: async (name) => window.localStorage.removeItem(name),
};

const THE_KEY = sessionKeyIn(THIS_BROWSER);

export const keptKey = THE_KEY.kept;

export const keepKey = THE_KEY.keep;

export const forgetKey = THE_KEY.forget;

const CORNER_UNDER = "pinecall.corner";

/** The colleague's sandbox corner this tab is viewing, or null. Per tab on purpose. */
export function keptCorner(): string | null {
  return window.sessionStorage.getItem(CORNER_UNDER);
}

export function keepCorner(corner: string | null): void {
  if (corner === null) window.sessionStorage.removeItem(CORNER_UNDER);
  else window.sessionStorage.setItem(CORNER_UNDER, corner);
}
