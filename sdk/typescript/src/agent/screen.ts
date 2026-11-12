/** A screen: what an agent puts on the caller's page, as named parts the page draws its own way. */

import { Fragment, jsx, type Child, type Component, type Element, type Props } from "../views/jsx-runtime.js";

import type { ToolSpec } from "../wire/defs.js";

import { DeclarationRefused, toolsOf } from "./tools.js";

/** One part of a screen as the page reads it: its name, what it was given, and what it holds. */
export interface ScreenNode {
  part: string;
  props: Record<string, unknown>;
  children: Screen;
}

/** A whole screen: its parts and the words between them, in order. */
export type Screen = (ScreenNode | string)[];

/** A part of the agent's own: a tag (`<Agenda slots={…} />`) that is also a function (`Agenda({ slots })`). */
export interface Part<P extends object> {
  (props: P & { children?: Child }): Element;
  readonly part: string;
}

/** What a tool stopped to ask the caller for, for a screen that draws the question as a form. */
export interface Asked {
  /** The task's name: the page gives it back in its `task.give`. */
  task: string;
  asks: string;
  /** What is to be given, each field with what it is. */
  fields: Record<string, string>;
  /** Why what the page gave last was refused, until it gives again. */
  refused?: string;
}

/** The field of a call's state its screen travels in, public to the caller's own page. */
export const SCREEN = "screen";

/** The event a page answers a task with: `call.event("task.give", { task: "phone", given: { number } })`. */
export const TASK_GIVE = "task.give";

const A_NAME = /^[a-z][a-z0-9-]*$/;

/**
 * Declare a part: `const Agenda = part<{ slots: Slot[] }>("agenda")`. The name is what the page maps
 * to a component of its own; what it is given must be plain data, since it crosses to a browser.
 */
export function part<P extends object = Record<never, never>>(name: string): Part<P> {
  if (!A_NAME.test(name)) throw new DeclarationRefused(`a part's name is lowercase letters, digits and dashes, and "${name}" is not: it is what the page maps to its component`);
  const tag = (props: P & { children?: Child }): Element => jsx(tag as unknown as Component, props as Props);
  return Object.assign(tag, { part: name });
}

/** Whether the class draws a screen of its own. */
export function drawsScreen(ctor: Function, base: Function): boolean {
  return (ctor.prototype as { screen?: unknown }).screen !== (base.prototype as { screen?: unknown }).screen;
}

/** What a `screen()` returned, as the parts a page reads. A component that is no part is called; a lowercase tag is its children. */
export function screenOf(child: Child): Screen {
  if (child === null || child === undefined || typeof child === "boolean") return [];
  if (typeof child === "string") return child.trim() === "" ? [] : [child.trim()];
  if (typeof child === "number") return [String(child)];
  if (Array.isArray(child)) return child.flatMap(screenOf);
  const { type, props } = child;
  const inside = (props["children"] ?? null) as Child;
  if (type === Fragment || typeof type !== "function") return screenOf(inside);
  const name = (type as Partial<Part<object>>).part;
  if (name === undefined) return screenOf(type(props));
  const { children: _children, ...given } = props;
  return [{ part: name, props: plain(given), children: screenOf(inside) }];
}

// What crosses to a browser is JSON: a function or an undefined given to a part is left behind.
function plain(given: Props): Record<string, unknown> {
  return JSON.parse(JSON.stringify(given)) as Record<string, unknown>;
}

/** The tool the model moves the caller's screen with, offered to a class that declares `scenes`. */
export const SHOW_SCREEN = "show_screen";

/** The scene that takes what a tool put up away: the screen with nothing chosen. */
export const NO_SCENE = "none";

const A_SCENE = /^[a-z][a-z0-9_-]*$/;

/** The scenes a class declares, checked against its tools' `shows`; empty for a class that declares none. */
export function scenesOf(ctor: Function): Record<string, string> {
  const declared = (ctor as { scenes?: unknown }).scenes;
  if (declared === undefined) return {};
  if (typeof declared !== "object" || declared === null || Array.isArray(declared)) throw new DeclarationRefused(`${ctor.name}: scenes names each scene with what it shows: { agenda: "the open times you last read" }`);
  const scenes = declared as Record<string, unknown>;
  for (const [name, what] of Object.entries(scenes)) {
    if (!A_SCENE.test(name) || name === NO_SCENE) throw new DeclarationRefused(`${ctor.name}: a scene is named in lowercase, and not "${NO_SCENE}": "${name}" is not one`);
    if (typeof what !== "string" || what.trim() === "") throw new DeclarationRefused(`${ctor.name}: the scene ${name} says what it shows, in words`);
  }
  return scenes as Record<string, string>;
}

/** The scene a tool of the class puts up, checked to be one of its scenes. */
export function shownBy(agent: object, tool: string): string | undefined {
  const declared = toolsOf(agent).find((one) => one.name === tool);
  const scene = declared?.options.shows;
  if (scene === undefined) return undefined;
  const scenes = scenesOf(agent.constructor);
  if (!(scene in scenes)) throw new DeclarationRefused(`${agent.constructor.name}.${tool} shows ${scene}, which is none of its scenes`);
  return scene;
}

/** The tool the model moves the screen with: one of the scenes, or `none`. */
export function showingTool(scenes: Record<string, string>): ToolSpec {
  const listed = Object.entries(scenes).map(([name, what]) => `${name}: ${what}`).join("; ");
  return {
    name: SHOW_SCREEN,
    description: `Put a scene on the caller's screen, or keep the one there, in the same turn as your words. ${listed}; ${NO_SCENE}: nothing chosen.`,
    parameters: { type: "object", properties: { scene: { type: "string", enum: [...Object.keys(scenes), NO_SCENE] } }, required: ["scene"] },
    side_effect: "read",
    quiet: true,
  };
}

/** What the model reads of the screen in this turn; empty for a class with no scenes. */
export function sceneLine(scenes: Record<string, string>, scene: string | null): string {
  if (Object.keys(scenes).length === 0) return "";
  if (scene === null) return `The caller's screen shows no scene. Put one up with ${SHOW_SCREEN} when it helps them.`;
  return `The caller's screen shows ${scene} (${scenes[scene] ?? scene}). It goes away when you answer about something else; call ${SHOW_SCREEN} to keep it or to show another.`;
}
