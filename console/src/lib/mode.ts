/** Which world this page is — production at the root, the sandbox under `/sandbox` — and the one table of what each has. */

/** The two worlds a gateway holds. The page names its world on every request (@pinecall/core/api). */
export type World = "production" | "sandbox";

// One gateway, one name, two worlds: the world of a page is the first segment of its path.
// `https://<name>/calls` is production's Calls and `https://<name>/sandbox/calls` the sandbox's —
// the same screens under the `/sandbox` prefix, at the same origin, on the same key. Only the
// router moves: the doors stay at the origin's root (`/v1/...`, lib/base.ts) whichever world the
// page is, and every request names its world in `pinecall-env`.
const THE_SANDBOXS_SEGMENT = "sandbox";

/** The world a page at that path is: `/sandbox` and everything under it is the sandbox's. */
export function worldOf(pathname: string): World {
  return pathname.split("/").filter(Boolean)[0] === THE_SANDBOXS_SEGMENT ? "sandbox" : "production";
}

/** The router's base in that world: production's screens at the root, the sandbox's under `/sandbox`. */
export function baseOf(world: World): string {
  return world === "sandbox" ? `/${THE_SANDBOXS_SEGMENT}` : "/";
}

/** A router path (`/calls/call_9f`) as the browser's own, in that world. */
export function inTheWorld(world: World, pathname: string): string {
  const base = baseOf(world);
  return base === "/" ? pathname : `${base}${pathname}`;
}

/** The browser's path as the router's: its world's prefix taken off. */
export function pageOf(pathname: string): string {
  return worldOf(pathname) === "sandbox" ? pathname.slice(baseOf("sandbox").length) || "/" : pathname;
}

/** The same screen in the other world: the browser's path with `/sandbox` taken off or put on. */
export function inTheOtherWorld(pathname: string): string {
  return inTheWorld(worldOf(pathname) === "sandbox" ? "production" : "sandbox", pageOf(pathname));
}

// The tests import this module in node, where there is no window at all: a page that was never
// rendered is production's, as a page at the root is in a browser.
/** Read once, when the page loads: the world this path is. */
export const WORLD: World = typeof window === "undefined" ? "production" : worldOf(window.location.pathname);

/** The router's base for this page's world (never an API URL's: those are lib/base.ts's). */
export const WORLD_BASE: string = baseOf(WORLD);

/**
 * The name this box is known by from OUTSIDE: what a widget tag pasted into a customer's site
 * loads from, and what an identity provider is registered with. One name serves both worlds, so
 * it is this page's origin and never a path under it: a site is handed the box, not a world.
 */
export function theBoxsOwnName(): string {
  return window.location.origin;
}

/** The sidebar's icons, by name (ui/icon.tsx). */
export type ScreenIcon = "home" | "grid" | "activity" | "list" | "chart" | "phone" | "key" | "plug" | "users" | "building" | "server" | "route" | "sliders" | "check" | "memory" | "words" | "book" | "headphones" | "persona" | "bell" | "chat" | "flask" | "bot" | "scale" | "shield";

/**
 * Where a row sits in the sidebar. Unmarked rows are what is LOOKED AT — Overview, Calls, Quality —
 * and read the same with every agent in view or one. `build` is what makes one agent, drawn only
 * while one is in view; `harness` is how an agent is put to the test and watched — simulations,
 * the callers they play, the real calls a judge broke on, the judges and the monitors — drawn
 * whoever is in view; `workspace` is
 * the org's own, drawn at the sidebar's foot whatever is; `yours` is the person's, not the org's,
 * reached from their own name at the very foot.
 */
export type ScreenGroup = "build" | "harness" | "workspace" | "yours";

/**
 * One screen: where it is, what it is called, which console has it, and where it sits. A screen
 * with no `under` is a ROW of the sidebar; one that names another screen is a TAB of that row,
 * reached through the tab bar drawn over the row's screens and never from the sidebar. A row that
 * is only a place for its tabs (`Test`, `Knowledge`, the org's `Settings`) opens on its first tab.
 */
export interface Screen {
  /** The key the scopes table gates it by (@pinecall/core/scopes). */
  key: string;
  path: string;
  name: string;
  in: readonly World[];
  icon?: ScreenIcon;
  /** The key of the row this screen is a tab of. */
  under?: string;
  /** A row with no screen of its own: its path lands on the first of its tabs. */
  opensOn?: "first-tab";
  /** What a row that is also a screen is called in its own tab bar, when its name would say the row twice. */
  tab?: string;
  group?: ScreenGroup;
  /** The box's own: drawn and routed only for a person the box made an operator. */
  operator?: true;
}

const BOTH = ["production", "sandbox"] as const;
const PRODUCTIONS = ["production"] as const;
const THE_WORKSHOPS = ["sandbox"] as const;

// THE table. The sidebar draws its rows, the tab bar draws the tabs under the row on screen, and
// the router routes every one of them — so a screen a console does not have is neither linked nor
// reachable by typing its path. A redesign moves rows here and nothing else: no screen asks which
// world it is in to decide whether it exists.
//
// One word, one place. What is looked at — Overview, Calls, Quality — is the same three rows
// whether every agent is in view or one, and the agent is what the sidebar's Viewing picks, never
// a section of its own: these are the org's, at the root, and the agent's below are the same
// screens under `/a/<slug>`. Agents lists them all, with the apps the box runs for the org and the
// secrets those start with: what is running, and how. Knowledge is every base and every fact of
// the world, the same row and tabs an agent has with only its own. The harness is the same five
// rows in both tables; with every agent in view each lists every agent's — every simulated call,
// every caller, every case, the org's judges and monitors — and a row opens what it lists under
// its own agent.
// What runs the org — numbers, people, the bill, its data and its rights, and Settings, what is set
// once and rarely — is the workspace, at the sidebar's foot; tokens and provider keys are each
// instance's own, so each console holds them. What the bell tells a person is theirs, not the org's.
export const ORG_SCREENS: readonly Screen[] = [
  { key: "overview", path: "", name: "Overview", in: BOTH, icon: "grid" },
  { key: "calls", path: "calls", name: "Calls", in: BOTH, icon: "list" },
  { key: "quality", path: "quality", name: "Quality", in: BOTH, icon: "check" },
  { key: "observability", path: "observability", name: "Observability", in: BOTH, icon: "activity" },
  { key: "agents", path: "agents", name: "Agents", in: BOTH, icon: "bot" },
  // The apps the box hosts for the org in this world (`pinecall deploy`), and what they start with.
  { key: "apps", path: "apps", name: "Apps", in: BOTH, under: "agents" },
  { key: "secrets", path: "secrets", name: "Secrets", in: BOTH, under: "agents" },
  // The agents built with no code, and where a new one is made; with an agent in view it is that agent's definition.
  { key: "studio", path: "studio", name: "Studio", in: BOTH, icon: "route" },
  // Every base of the world and who searches it, and every fact any agent's calls taught.
  { key: "knowledge", path: "knowledge", name: "Knowledge", in: BOTH, icon: "book", opensOn: "first-tab" },
  { key: "org-docs", path: "docs", name: "Docs", in: BOTH, under: "knowledge" },
  { key: "org-memory", path: "memory", name: "Memory", in: BOTH, under: "knowledge" },
  { key: "simulations", path: "simulations", name: "Simulations", in: BOTH, icon: "headphones", group: "harness" },
  { key: "personas", path: "personas", name: "Personas", in: BOTH, icon: "persona", group: "harness" },
  { key: "cases", path: "cases", name: "Cases", in: BOTH, icon: "flask", group: "harness" },
  { key: "judges", path: "judges", name: "Judges", in: BOTH, icon: "scale", group: "harness" },
  { key: "monitors", path: "monitors", name: "Monitors", in: BOTH, icon: "bell", group: "harness" },
  { key: "numbers", path: "numbers", name: "Numbers", in: PRODUCTIONS, icon: "phone", group: "workspace" },
  { key: "team", path: "team", name: "Team", in: PRODUCTIONS, icon: "users", group: "workspace" },
  { key: "usage", path: "usage", name: "Usage", in: PRODUCTIONS, icon: "chart", group: "workspace" },
  // The org's data, a tab each: its rules and what a call says first, who may be called, the world
  // exported and a contact erased with the trail of every erasure, and who read what.
  { key: "org-data", path: "data", name: "Privacy", in: BOTH, icon: "shield", opensOn: "first-tab", group: "workspace" },
  { key: "data-rules", path: "data/rules", name: "Rules", in: BOTH, under: "org-data" },
  { key: "data-consent", path: "data/consent", name: "Consent", in: BOTH, under: "org-data" },
  { key: "data-erasures", path: "data/erasures", name: "Export & erase", in: BOTH, under: "org-data" },
  { key: "data-reads", path: "data/reads", name: "Access log", in: BOTH, under: "org-data" },
  { key: "org-settings", path: "settings", name: "Settings", in: BOTH, icon: "sliders", opensOn: "first-tab", group: "workspace" },
  { key: "tokens", path: "tokens", name: "API keys", in: BOTH, under: "org-settings" },
  { key: "providers", path: "providers", name: "Providers", in: BOTH, under: "org-settings" },
  { key: "telemetry", path: "telemetry", name: "Telemetry", in: BOTH, under: "org-settings" },
  // Where the org's alerts are posted: a webhook of its own, beside the bell.
  { key: "alerts", path: "alerts", name: "Alerts", in: BOTH, under: "org-settings" },
  { key: "phone", path: "phone", name: "Phone testing", in: THE_WORKSHOPS, under: "org-settings" },
  // What the bell tells this person, on every device of theirs: opened from their name.
  { key: "notifications", path: "notifications", name: "Notifications", in: BOTH, icon: "bell", group: "yours" },
];

// The BOX's screens: every tenant, the fleet under them, the doors, the bill of all of them, and
// what the box itself is set to. They are not an org's — an org's admin never sees them — so they
// are a table of their own, each row marked: only a person the box made an operator is shown one.
export const BOX_SCREENS: readonly Screen[] = [
  { key: "box-orgs", path: "box/orgs", name: "Organizations", in: PRODUCTIONS, icon: "building", operator: true },
  { key: "box-fleet", path: "box/fleet", name: "Fleet", in: PRODUCTIONS, icon: "server", operator: true },
  { key: "box-carriers", path: "box/carriers", name: "Carriers", in: PRODUCTIONS, icon: "phone", operator: true },
  { key: "box-routes", path: "box/routes", name: "Routes", in: PRODUCTIONS, icon: "route", operator: true },
  { key: "box-traceback", path: "box/traceback", name: "Traceback", in: PRODUCTIONS, icon: "phone", operator: true },
  { key: "box-usage", path: "box/usage", name: "Box usage", in: PRODUCTIONS, icon: "chart", operator: true },
  { key: "box-settings", path: "box/settings", name: "Box settings", in: PRODUCTIONS, icon: "sliders", operator: true },
];

// One agent in view: the same three rows the org's are — its Overview, its Calls, its Quality,
// each the org's screen with only its calls — then what builds it. Studio is an agent built with no
// code, its definition a form beside the agent to talk to. Playground is the gateway's
// room, by voice or in writing, and Dev chat — a written call to the class in a developer's own
// directory — is its second tab in the workshop. Test is what happens before a change ships: the
// goldens and their runs, with an overview of the whole harness first. The harness is its own
// rows: a caller put on it live, the callers written for it, the real calls a judge broke on
// waiting for a person, the judges its real calls are held to, and the monitors over them.
// Knowledge is what it searches and what it learned. Configure is what it runs on; the pipeline
// that results, its lexicon and the widget that embeds it are a row each, beside it.
export const AGENT_SCREENS: readonly Screen[] = [
  { key: "agent-overview", path: "overview", name: "Overview", in: BOTH, icon: "grid" },
  { key: "calls", path: "calls", name: "Calls", in: BOTH, icon: "list" },
  { key: "quality", path: "quality", name: "Quality", in: BOTH, icon: "check" },
  // An agent built with no code: its definition edited in the sandbox beside a live preview, read in production.
  { key: "studio", path: "studio", name: "Studio", in: BOTH, icon: "bot", group: "build" },
  { key: "talk", path: "playground", name: "Playground", tab: "Chat", in: BOTH, icon: "chat", group: "build" },
  { key: "devchat", path: "dev-chat", name: "Dev chat", in: THE_WORKSHOPS, under: "talk" },
  { key: "test", path: "test", name: "Test", tab: "Overview", in: BOTH, icon: "flask", group: "build" },
  { key: "evals", path: "goldens", name: "Goldens", in: BOTH, under: "test" },
  { key: "knowledge", path: "knowledge", name: "Knowledge", in: BOTH, icon: "book", opensOn: "first-tab", group: "build" },
  { key: "docs", path: "docs", name: "Docs", in: BOTH, under: "knowledge" },
  { key: "memory", path: "memory", name: "Memory", in: BOTH, under: "knowledge" },
  { key: "settings", path: "configure", name: "Configure", in: BOTH, icon: "sliders", group: "build" },
  { key: "pipeline", path: "pipeline", name: "Pipeline", in: BOTH, icon: "activity", group: "build" },
  { key: "lexicon", path: "lexicon", name: "Lexicon", in: BOTH, icon: "words", group: "build" },
  { key: "widget", path: "widget", name: "Widget", in: BOTH, icon: "plug", group: "build" },
  { key: "simulations", path: "simulations", name: "Simulations", in: BOTH, icon: "headphones", group: "harness" },
  { key: "personas", path: "personas", name: "Personas", in: BOTH, icon: "persona", group: "harness" },
  // A real call a judge broke on waits here for a person.
  { key: "cases", path: "cases", name: "Cases", in: BOTH, icon: "flask", group: "harness" },
  { key: "judges", path: "judges", name: "Judges", in: BOTH, icon: "scale", group: "harness" },
  { key: "monitors", path: "monitors", name: "Monitors", in: BOTH, icon: "bell", group: "harness" },
];

/** The screens of a table this console has, in the table's order; an operator's only for an operator. */
export function screensOf(table: readonly Screen[], world: World = WORLD, operator = false): Screen[] {
  return table.filter((screen) => screen.in.includes(world) && (operator || screen.operator !== true));
}

/** Whether this console has that screen, by its key. */
export function has(table: readonly Screen[], key: string, world: World = WORLD): boolean {
  return table.some((screen) => screen.key === key && screen.in.includes(world));
}

/** The sidebar's rows of a table: the screens that are not a tab of another. */
export function rowsOf(table: readonly Screen[], world: World = WORLD, operator = false): Screen[] {
  return screensOf(table, world, operator).filter((screen) => screen.under === undefined);
}

/** A row's tabs: the row itself where it is a screen, then every screen that is under it. */
export function tabsOf(table: readonly Screen[], row: Screen, world: World = WORLD): Screen[] {
  const own = row.opensOn === "first-tab" ? [] : [row];
  return [...own, ...screensOf(table, world).filter((screen) => screen.under === row.key)];
}

/** What a row is called in its own tab bar: its `tab` word where its name would say the row twice. */
export function tabName(screen: Screen): string {
  return screen.under === undefined ? (screen.tab ?? screen.name) : screen.name;
}

/** The row a screen belongs to: itself, or the one it is a tab of. */
export function rowOf(table: readonly Screen[], screen: Screen): Screen {
  return (screen.under === undefined ? undefined : table.find((one) => one.key === screen.under)) ?? screen;
}

// A path is a screen's when it starts with that screen's own path, once an agent's prefix is off
// it: `/calls/call_9f` is Calls', `/a/clinica-norte/calls/call_9f` the same screen with one agent
// in view. The longest match wins, so `box/orgs` is not mistaken for anything shorter — and the
// table is the path's, because an agent's `docs` and the org's are two screens at one word. What a back link is
// CALLED comes from here, which is why a screen renamed in the table is renamed in every link
// pointing home to it.
/** The screen a path belongs to, or undefined when no screen owns it. */
export function screenAt(path: string): Screen | undefined {
  const bare = path.split(/[?#]/)[0] ?? "";
  const ofAnAgent = /^\/a\/[^/]+/.test(bare);
  const table = ofAnAgent ? AGENT_SCREENS : [...ORG_SCREENS, ...BOX_SCREENS];
  const under = bare.replace(/^\/a\/[^/]+\/?/, "/").replace(/^\/+/, "");
  const cut = under.replace(/\/$/, "");
  if (cut === "") return table.find((screen) => screen.path === "");
  return table.filter((screen) => screen.path !== "" && (cut === screen.path || cut.startsWith(`${screen.path}/`))).sort(
    (one, other) => other.path.length - one.path.length,
  )[0];
}
