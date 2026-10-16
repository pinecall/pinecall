/** Light/dark theme: follow the system, with a persisted flip (console) or choice (mobile). */

export type Theme = "dark" | "light";

/** An explicit theme, or "auto" to follow the system. */
export type ThemeChoice = "auto" | Theme;

// `systemWas` lets a later visit detect that the system theme changed and drop the flip.
interface Kept {
  theme: Theme;
  systemWas: Theme;
}

const KEPT_UNDER = "pinecall.theme";

// A choice persists across system changes; a flip does not. An app uses one or the other.
const CHOSEN_UNDER = "pinecall.theme-choice";

const SYSTEM_LIGHT = "(prefers-color-scheme: light)";

function systemTheme(): Theme {
  return window.matchMedia(SYSTEM_LIGHT).matches ? "light" : "dark";
}

function stamp(theme: Theme): void {
  document.documentElement.dataset["theme"] = theme;
}

function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

// Storage may throw (private window, blocked site data); the theme then lasts only for the page.
function kept(name: string): string | null {
  try {
    return window.localStorage.getItem(name);
  } catch {
    return null;
  }
}

function keep(name: string, value: string): void {
  try {
    window.localStorage.setItem(name, value);
  } catch {
    // Storage unavailable.
  }
}

function forget(name: string): void {
  try {
    window.localStorage.removeItem(name);
  } catch {
    // Storage unavailable.
  }
}

/** The stored flip, if the system theme hasn't changed since it was made. */
function keptTheme(): Theme | null {
  let flip: Partial<Kept> | null = null;
  try {
    flip = JSON.parse(kept(KEPT_UNDER) ?? "null") as Partial<Kept> | null;
  } catch {
    return null;
  }
  if (flip === null || !isTheme(flip.theme) || flip.systemWas !== systemTheme()) {
    forget(KEPT_UNDER);
    return null;
  }
  return flip.theme;
}

/** Apply the stored flip or the system theme; a system change clears the flip. */
export function followTheSystemTheme(): void {
  stamp(keptTheme() ?? systemTheme());
  // Never unsubscribed: lives as long as the document.
  window.matchMedia(SYSTEM_LIGHT).addEventListener("change", () => {
    forget(KEPT_UNDER);
    stamp(systemTheme());
  });
}

/** The document's current theme. */
export function currentTheme(): Theme {
  return document.documentElement.dataset["theme"] === "light" ? "light" : "dark";
}

/** Toggle and persist the theme; returns the new one. Flipping back to the system theme clears it. */
export function toggleTheme(): Theme {
  const next: Theme = currentTheme() === "dark" ? "light" : "dark";
  const system = systemTheme();
  if (next === system) forget(KEPT_UNDER);
  else keep(KEPT_UNDER, JSON.stringify({ theme: next, systemWas: system } satisfies Kept));
  stamp(next);
  return next;
}

// Held in memory so the choice survives a failed storage write until the page closes.
let chosen: ThemeChoice = "auto";

function keptChoice(): ThemeChoice {
  const choice = kept(CHOSEN_UNDER);
  return isTheme(choice) ? choice : "auto";
}

function wear(choice: ThemeChoice): void {
  stamp(choice === "auto" ? systemTheme() : choice);
}

/** Apply the stored choice, tracking the system theme while it is "auto". */
export function wearTheChosenTheme(): void {
  chosen = keptChoice();
  wear(chosen);
  // Never unsubscribed: lives as long as the document.
  window.matchMedia(SYSTEM_LIGHT).addEventListener("change", () => {
    if (chosen === "auto") stamp(systemTheme());
  });
}

/** The current choice; "auto" by default. */
export function chosenTheme(): ThemeChoice {
  return chosen;
}

/** Set, persist and apply a choice; returns the resulting theme. */
export function chooseTheme(choice: ThemeChoice): Theme {
  chosen = choice;
  if (choice === "auto") forget(CHOSEN_UNDER);
  else keep(CHOSEN_UNDER, choice);
  wear(choice);
  return currentTheme();
}

/** Observe `data-theme` changes on the document; returns an unsubscribe function. */
export function watchTheme(changed: () => void): () => void {
  const watching = new MutationObserver(changed);
  watching.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => watching.disconnect();
}
