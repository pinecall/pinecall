/** A call's screen as the bridge keeps it: drawn from the agent, sent in the call's state when it changed. */

import { Agent } from "../agent/agent.js";
import { drawsScreen, NO_SCENE, SCREEN, scenesOf, screenOf, SHOW_SCREEN, showingTool, shownBy, TASK_GIVE, type Screen } from "../agent/screen.js";
import { DeclarationRefused, toolsOf } from "../agent/tools.js";
import type { CallWorld } from "../call/call.js";
import type { ToolSpec } from "../wire/defs.js";
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
  /** Whether the turn going on now was opened by the caller, and whether something in it kept the scene. */
  byUser?: boolean;
  kept?: boolean;
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

/** The tool a class moves its screen with, declared once for the classes of a call; each is checked against its own scenes. */
export function sceneTools(classes: readonly Function[], taken: readonly string[]): ToolSpec[] {
  const scenes: Record<string, string> = {};
  for (const ctor of classes) {
    Object.assign(scenes, scenesOf(ctor));
    // A probe, as mount makes one: the tools are read off an instance's prototype chain.
    for (const declared of toolsOf(new (ctor as new () => object)())) {
      const shows = declared.options.shows;
      if (shows !== undefined && !(shows in scenesOf(ctor))) throw new DeclarationRefused(`${ctor.name}.${declared.name} shows ${shows}, which is none of its static scenes`);
    }
  }
  if (Object.keys(scenes).length === 0) return [];
  if (taken.includes(SHOW_SCREEN)) throw new DeclarationRefused(`${SHOW_SCREEN} is the tool a screen is moved with, and an agent declares a tool of that name`);
  return [showingTool(scenes)];
}

/** The tool the class serving the call moves its screen with, when it declares scenes. */
export function sceneToolOf(ctor: Function): ToolSpec[] {
  const scenes = scenesOf(ctor);
  return Object.keys(scenes).length === 0 ? [] : [showingTool(scenes)];
}

/** The model chose a scene, or none: it is the call's now, and kept through this turn. */
export function sceneChosen(world: CallWorld, screened: Screened, ctor: Function, args: Record<string, unknown>, drawn: () => void): string {
  const scene = String(args["scene"] ?? "");
  if (scene !== NO_SCENE && !(scene in scenesOf(ctor))) return `There is no scene ${scene}: ${[...Object.keys(scenesOf(ctor)), NO_SCENE].join(", ")}.`;
  world.scene = scene === NO_SCENE ? null : scene;
  screened.kept = true;
  drawn();
  return "shown";
}

/** Run a tool that shows a scene: the scene is kept through the turn from the tool's start, and put up once its function returned. */
export async function showing<T>(agent: Agent, screened: Screened, tool: string, running: () => Promise<T>): Promise<T> {
  const scene = shownBy(agent, tool);
  if (scene === undefined) return running();
  screened.kept = true;
  const result = await running();
  agent.call.scene = scene;
  return result;
}

/**
 * A turn of the call went by. One the caller opened, in which no tool showed the scene and the model did
 * not keep it, takes the scene away: the screen follows the conversation. True when the scene moved. Read
 * at `agent.waiting`, once every sentence and every tool of the answer is done: a tool's announcement is
 * a `turn.agent` of its own, written before the tool runs.
 */
export function turned(type: string, world: CallWorld, screened: Screened): boolean {
  if (type === "turn.user") {
    Object.assign(screened, { byUser: true, kept: false });
    return false;
  }
  if (type !== "agent.waiting" || screened.byUser !== true) return false;
  screened.byUser = false;
  if (screened.kept === true || world.scene === null) return false;
  world.scene = null;
  return true;
}
