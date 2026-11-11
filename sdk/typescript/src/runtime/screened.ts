/** A call's screen as the bridge keeps it: drawn from the agent, sent in the call's state when it changed. */

import { Agent } from "../agent/agent.js";
import { drawsScreen, SCREEN, screenOf, TASK_GIVE, type Screen } from "../agent/screen.js";
import { snapshot, type Snapshot } from "../agent/state.js";
import type { AgentOptions } from "../client/index.js";
import type { Child } from "../views/jsx-runtime.js";

import type { Asking } from "./asking.js";
import type { Serving } from "./dispatch.js";

/** The screen a call's page was last sent. */
export interface Screened {
  screen?: Screen;
  /** The screen as text, to tell a new one from the one sent. */
  key?: string;
}

const EMPTY = "[]";

/** Whether the class, or one of its team, draws a screen: its field is then public, and a page may give a task. */
export function screens(ctor: Function, team?: ReadonlyMap<Function, string>): boolean {
  return (team === undefined ? [ctor] : [...team.keys()]).some((one) => drawsScreen(one, Agent));
}

/** What the gateway is told a class with a screen declares: the field's visibility, and with tasks the page's event. */
export function screenDeclared(options: AgentOptions, tasks: boolean): AgentOptions {
  const stateFields = [...(options.stateFields ?? []), { name: SCREEN, visibility: "public" as const }];
  const events = tasks ? [...(options.events ?? []), { name: TASK_GIVE, from: ["participant" as const] }] : options.events;
  return { ...options, stateFields, ...(events === undefined ? {} : { events }) };
}

/** Draw the agent's screen, with what it shows over it; true when it is not the one already sent. */
export function redrawn(agent: Agent, screened: Screened): boolean {
  const screen = screenOf([agent.screen(), agent.call.shown as Child]);
  const key = JSON.stringify(screen);
  if (key === (screened.key ?? EMPTY)) return false;
  Object.assign(screened, { screen, key });
  return true;
}

/** The call's state as the gateway is told it: the agent's own, and its screen once it drew one. */
export function stateWith(agent: Agent, screened: Screened): Snapshot {
  return screened.screen === undefined ? snapshot(agent) : { ...snapshot(agent), [SCREEN]: screened.screen };
}

/** A state the gateway kept, without the screen: it is drawn again, never restored into the agent. */
export function unscreened(state: Snapshot): Snapshot {
  const { [SCREEN]: _screen, ...own } = state;
  return own;
}

/** The page answered a task: the waiting tool goes on, and the model is told how it ended. True when the event was that. */
export async function givenByPage(serving: Serving, asking: Asking, name: string, source: string, data: Record<string, unknown>): Promise<boolean> {
  if (name !== TASK_GIVE || source !== "participant") return false;
  const told = await asking.givenByPage(data["task"], data["given"]);
  if (told !== undefined) void serving.call.reply(told);
  return true;
}
