/** A screen: what an agent puts on the caller's page, as named parts the page draws its own way. */

import { Fragment, jsx, type Child, type Component, type Element, type Props } from "../views/jsx-runtime.js";

import { DeclarationRefused } from "./tools.js";

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
