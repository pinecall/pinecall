/** The page as the agent reads it: Playwright's aria snapshot, kept small, with a ref on what can be pointed at. */
//
// One line per thing a person would name, indented by what holds it: roles and names, not markup.
// What is on the screen is there in full; a section out of view is one line, its name and whether
// it is above or below, so the agent knows it is there and can scroll to it. A ref is stable for
// the page's life. Fields are their labels; passwords, card numbers and anything the site marks
// `data-pinecall-skip` or `aria-hidden` are left out.

import { SAID_WHOLE, nameOf, roleOf } from "./roles.js";

/** What `seen()` returns: the text the agent reads, and its size. */
export interface Seen {
  text: string;
  bytes: number;
  lines: number;
}

/** The roles that get a ref: what the agent can point at, scroll to, or highlight. */
const POINTABLE = new Set(["link", "button", "textbox", "combobox", "checkbox", "radio", "heading", "article", "region", "img", "form", "group"]);
/** Kept as a line even with no name, because they say where things are. */
const LANDMARKS = new Set(["banner", "navigation", "main", "contentinfo", "form", "list", "group"]);
/** Always walked, on screen or not: a sticky header, the page's frame. */
const FRAME = new Set(["banner", "navigation", "main"]);
const IGNORED = "script, style, template, audio, video, svg, noscript";

export class Page {
  readonly #document: Document;
  readonly #refs = new WeakMap<Element, string>();
  /** Every ref ever given, so one the agent holds still names its element after a scroll took it off the screen. */
  readonly #given = new Map<string, WeakRef<Element>>();
  /** The refs the last `seen()` showed, which `find()` looks through. */
  #byRef = new Map<string, Element>();
  #next = 1;

  constructor(document: Document) {
    this.#document = document;
  }

  /** The page as text, now. Refs given before are given again to the same elements. */
  seen(): Seen {
    this.#byRef = new Map();
    const view = this.#document.defaultView;
    const height = view?.innerHeight ?? 0;
    const top = Math.round(view?.scrollY ?? 0);
    const total = Math.round(this.#document.documentElement.scrollHeight);
    const lines = [`- page "${this.#document.title}" (scrolled ${top}–${top + Math.round(height)} of ${total}px)`];
    this.#walk(this.#document.body, 0, height, lines);
    const text = lines.join("\n");
    return { text, bytes: new TextEncoder().encode(text).length, lines: lines.length };
  }

  /** The element a ref names, while it is on the page; null once it is gone. */
  element(ref: string): Element | null {
    const element = this.#given.get(ref)?.deref();
    return element !== undefined && element.isConnected ? element : null;
  }

  /** The ref of the first element of `role` whose name holds `name`, in the last `seen()`. */
  find(role: string, name: string): string | null {
    const wanted = name.toLowerCase();
    for (const [ref, element] of this.#byRef) {
      const own = roleOf(element);
      if (own === role && nameOf(element, own).toLowerCase().includes(wanted)) return ref;
    }
    return null;
  }

  /**
   * The ref of what a person would mean by `name`, in the last `seen()`: the name said exactly, else one
   * that starts with it, else one that holds it, a section before a heading before a card, a button
   * or a link when several share it.
   */
  named(name: string): string | null {
    const wanted = name.trim().toLowerCase();
    if (wanted === "") return null;
    const candidates = [...this.#byRef].map(([ref, element]) => {
      const role = roleOf(element) ?? "";
      return { ref, role, name: nameOf(element, role).toLowerCase() };
    });
    for (const fits of [(one: string) => one === wanted, (one: string) => one.startsWith(wanted), (one: string) => one.includes(wanted)]) {
      const found = candidates.filter((one) => fits(one.name)).sort((a, b) => rank(a.role) - rank(b.role))[0];
      if (found !== undefined) return found.ref;
    }
    return null;
  }

  #ref(element: Element): string {
    let ref = this.#refs.get(element);
    if (ref === undefined) {
      ref = `e${this.#next}`;
      this.#next += 1;
      this.#refs.set(element, ref);
      this.#given.set(ref, new WeakRef(element));
    }
    this.#byRef.set(ref, element);
    return ref;
  }

  #walk(parent: Element, depth: number, height: number, lines: string[]): void {
    for (const child of parent.children) {
      if (child.matches(IGNORED) || left(child)) continue;
      const role = roleOf(child);
      const name = role === null ? "" : nameOf(child, role);
      const box = child.getBoundingClientRect();
      const visible = box.bottom > 0 && box.top < height && box.width > 0 && box.height > 0;
      const indent = "  ".repeat(depth);
      if (role === "region" && !visible) {
        lines.push(`${indent}- region "${name}" [ref=${this.#ref(child)}] (${box.top > 0 ? "below" : "above"})`);
        continue;
      }
      const kept = role !== null && (name !== "" || LANDMARKS.has(role));
      if (!kept) {
        this.#walk(child, depth, height, lines);
        continue;
      }
      if (!visible && !FRAME.has(role)) continue;
      const parts = [`- ${role}`];
      if (name !== "") parts.push(`"${name.replaceAll('"', "'")}"`);
      if (role === "heading") parts.push(`[level=${child.tagName.slice(1)}]`);
      if (child instanceof HTMLDetailsElement) parts.push(child.open ? "[expanded]" : "[collapsed]");
      if (POINTABLE.has(role)) parts.push(`[ref=${this.#ref(child)}]`);
      lines.push(indent + parts.join(" "));
      if (!SAID_WHOLE.has(role)) this.#walk(child, depth + 1, height, lines);
    }
  }
}

/** Which of several things that share a name a person means first: the section, then its heading. */
const PREFERRED = ["region", "heading", "article", "button", "link", "form", "img", "group"];

function rank(role: string): number {
  const at = PREFERRED.indexOf(role);
  return at === -1 ? PREFERRED.length : at;
}

/** Out of the snapshot: hidden, marked by the site, or a secret. */
function left(element: Element): boolean {
  if (element.closest("[data-pinecall-skip], [aria-hidden='true']") !== null) return true;
  if (element instanceof HTMLInputElement && (element.type === "password" || element.autocomplete.startsWith("cc-"))) return true;
  const style = element.ownerDocument.defaultView?.getComputedStyle(element);
  return style !== undefined && (style.display === "none" || style.visibility === "hidden");
}
