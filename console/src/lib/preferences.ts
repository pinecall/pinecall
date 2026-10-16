/** What a person left set, kept by their browser — how wide each pane, how a call is read. Preferences, never a credential. */

const UNDER = "pinecall.pane.";

/** The width kept for a pane, or null when none was, it is not a number, or storage is closed. */
export function keptWidth(pane: string): number | null {
  try {
    const kept = Number(window.localStorage.getItem(UNDER + pane));
    return Number.isFinite(kept) && kept > 0 ? kept : null;
  } catch {
    return null;
  }
}

/** Keep a pane's width. A browser that refuses storage keeps nothing, and the page still works. */
export function keepWidth(pane: string, width: number): void {
  try {
    window.localStorage.setItem(UNDER + pane, String(Math.round(width)));
  } catch {
    // A private window: the width lasts as long as the page does.
  }
}

/** Forget a pane's width: it goes back to the one the screen was drawn with. */
export function forgetWidth(pane: string): void {
  try {
    window.localStorage.removeItem(UNDER + pane);
  } catch {
    // Nothing was kept.
  }
}

/** How a call's page reads it: as a chat, as the transcript, as the whole log, or as a trace on a time axis. */
export type CallView = "chat" | "transcript" | "log" | "trace";

const VIEW = "pinecall.call.view";
const VIEWS: readonly CallView[] = ["chat", "transcript", "log", "trace"];

/** The way this person last read a call, or null when they never picked one or storage is closed. */
export function keptCallView(): CallView | null {
  try {
    const kept = window.localStorage.getItem(VIEW);
    return VIEWS.find((view) => view === kept) ?? null;
  } catch {
    return null;
  }
}

/** Keep the way this person reads a call, for the next one they open. */
export function keepCallView(view: CallView): void {
  try {
    window.localStorage.setItem(VIEW, view);
  } catch {
    // A private window: the choice lasts as long as the page does.
  }
}

const WELCOME = "pinecall.welcome";

/** Whether this person went through the welcome guide, or skipped it, in this browser. */
export function welcomed(): boolean {
  try {
    return window.localStorage.getItem(WELCOME) === "yes";
  } catch {
    return false;
  }
}

/** Remember the guide was shown, so a new org is not sent to it again. */
export function markWelcomed(): void {
  try {
    window.localStorage.setItem(WELCOME, "yes");
  } catch {
    // A private window: the guide offers itself again next time.
  }
}

const LIBRARY = "pinecall.personas.library";

/** Whether Pinecall's library of personas is folded away: open unless this person folded it. */
export function libraryFolded(): boolean {
  try {
    return window.localStorage.getItem(LIBRARY) === "folded";
  } catch {
    return false;
  }
}

/** Keep the library folded or open, for the next time the screen is opened. */
export function keepLibraryFolded(folded: boolean): void {
  try {
    if (folded) window.localStorage.setItem(LIBRARY, "folded");
    else window.localStorage.removeItem(LIBRARY);
  } catch {
    // A private window: the choice lasts as long as the page does.
  }
}
