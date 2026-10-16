/** `@view(Component)`: the console panel an agent draws beside a conversation. */

import type { Child } from "../views/jsx-runtime.js";
import { DeclarationRefused } from "./tools.js";

/**
 * The conversation a panel is drawn for. It identifies a thread, not live call state: panels are
 * shown for ended calls too, so a view fetches its data from the tenant's own systems.
 */
export interface Who {
  /** The agent whose thread is open. */
  agent: string;
  /** The other party: phone number, contact id, or web visitor id. */
  contact: string;
  /** The thread's most recent call id. */
  call: string;
}

/** Draws a panel for one conversation with `@pinecall/agents/panels` tags. May be async. */
export type View = (who: Who) => Child | Promise<Child>;

/** A class's declared panel: its title and draw function. */
export interface DeclaredView {
  name: string;
  draw: View;
}

// Stored outside the class: subclasses do not inherit it and nothing is added to the tenant's class.
const VIEWS = new WeakMap<object, DeclaredView>();

/**
 * Declare the class's console panel. The title defaults to the function name spaced out
 * (`CustomerCard` becomes "Customer Card"); pass `name` to set it.
 */
export function view(draw: View, name?: string) {
  return function decorate(ctor: new (...args: never[]) => object): void {
    const standing = VIEWS.get(ctor);
    if (standing !== undefined) {
      throw new DeclarationRefused(`${ctor.name} declares two views (${standing.name} and ${name ?? nameOf(draw)}); a class draws one panel`);
    }
    VIEWS.set(ctor, { name: name ?? nameOf(draw), draw });
  };
}

/** The class's declared panel, or undefined. */
export function viewOf(ctor: object): DeclaredView | undefined {
  return VIEWS.get(ctor);
}

// `CustomerCard` -> `Customer Card`; acronyms are left intact.

function nameOf(draw: View): string {
  const written = draw.name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").trim();
  if (written === "") return "View";
  return written.charAt(0).toUpperCase() + written.slice(1);
}
