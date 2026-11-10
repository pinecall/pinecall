/** The session key in this browser; the only module that touches its storage. */

import { sessionKeyIn, type KeyStorage } from "@pinecall/core/session-key";

const THIS_BROWSER: KeyStorage = {
  read: async (name) => window.localStorage.getItem(name),
  write: async (name, value) => window.localStorage.setItem(name, value),
  erase: async (name) => window.localStorage.removeItem(name),
};

const THE_KEY = sessionKeyIn(THIS_BROWSER);

export const keptKey = THE_KEY.kept;
export const keepKey = THE_KEY.keep;
export const forgetKey = THE_KEY.forget;

/** The label this console's keys carry in the org's key list. */
export const DEVICE = "console";

/** Where the gateway's doors are: this page's own origin, whichever world it is. */
export const API_BASE = "/";
