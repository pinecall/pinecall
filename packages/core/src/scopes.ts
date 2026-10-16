/** Which screens a key opens: the rail draws what the key's scopes open and nothing it would be refused. */

// The doors as the gateway groups them (runtime types/key.py), and the screen each one gates.
// A screen the key does not open is not drawn — never a 403 met on a click. The desk is gated
// inside the conversation page by `supervise`; nothing else here decides what a verb may do.
export const SCOPE_OF: Record<string, string> = {
  talk: "talk",
  devchat: "talk",
  calls: "calls",
  "agent-overview": "calls",
  pipeline: "pipeline",
  // Settings and the lexicon open to `pipeline` OR `words` at the gateway; every person's key that
  // holds either holds `words`, so the rail gates them by the one both sides have.
  settings: "words",
  lexicon: "words",
  docs: "knowledge",
  memory: "memory",
  evals: "evals",
  quality: "evals",
  judges: "evals",
  monitors: "evals",
  test: "evals",
  alerts: "providers",
  widget: "talk",
  agents: "calls",
  personas: "evals",
  simulations: "evals",
  "org-memory": "memory",
  "org-docs": "knowledge",
  numbers: "numbers",
  providers: "providers",
  team: "team",
  usage: "usage",
  "org-data": "team",
  "data-rules": "team",
  "data-consent": "team",
  "data-erasures": "team",
  "data-reads": "team",
};

/** Whether a key with these scopes opens this screen. A screen nobody gated is open. */
export function opens(scopes: readonly string[], screen: string): boolean {
  const scope = SCOPE_OF[screen];
  return scope === undefined || scopes.includes(scope);
}

/** The sentence a section a key does not open would say, if it were drawn at all. */
export function notOpened(screen: string): string {
  return `this key does not open ${SCOPE_OF[screen] ?? screen}`;
}

// Every scope a key may carry (runtime types/key.py). An operator's visit into an org holds every one
// but `app` — the box looks and mends, and holds no agent — so to a person reading a list, everything.
const EVERY_SCOPE = ["app", "calls", "evals", "keys", "knowledge", "memory", "numbers", "pipeline", "providers", "supervise", "talk", "team", "usage", "words"];

/** What a key may do, as one short line: "everything", or its scopes. */
export function scopesLine(scopes: readonly string[]): string {
  const missing = EVERY_SCOPE.filter((scope) => !scopes.includes(scope));
  if (missing.length === 0 || (missing.length === 1 && missing[0] === "app")) return "everything";
  return scopes.join(", ");
}
