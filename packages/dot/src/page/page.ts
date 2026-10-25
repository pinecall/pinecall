/** The page as the agent reads it: Playwright's aria snapshot, kept small, with a ref on what can be pointed at. */
//
// One line per thing a person would name, indented by what holds it: roles and names, not markup.
// Words in a box that is only layout, as a price, are a line of text, as Playwright says them.
// What is on the screen is there in full; a section out of view is one line, its name and whether
// it is above or below, so the agent knows it is there and can scroll to it. A ref is stable for
// the page's life. A field is its label and what it holds now, a list its options; passwords, card
// numbers and anything the site marks `data-pinecall-skip` or `aria-hidden` are left out. What the
// site wrote for the agent to say (`data-pinecall-say`) is marked, and read by `lines()`.

import { SAID_WHOLE, clean, nameOf, roleOf } from "./roles.js";
import type { Line } from "../wire/index.js";

/** What `seen()` returns: the text the agent reads, and its size. */
export interface Seen {
  text: string;
  bytes: number;
  lines: number;
}

/** The roles that get a ref: what the agent can point at, scroll to, or highlight. */
const POINTABLE = new Set(["link", "button", "tab", "textbox", "combobox", "checkbox", "radio", "heading", "article", "region", "img", "form", "group"]);
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

  /**
   * What the site wrote for the agent to say, each beside the element it is about: `data-pinecall-say`,
   * in `data-pinecall-order` and then in the page's order, with the move `data-pinecall-do` names
   * (`point` unless it says `highlight` or `scroll_to`).
   */
  lines(): Line[] {
    const marked = [...this.#document.body.querySelectorAll("[data-pinecall-say]")].filter((element) => !element.matches(IGNORED) && !left(element));
    const order = (element: Element): number => Number.parseFloat(element.getAttribute("data-pinecall-order") ?? "") || Number.POSITIVE_INFINITY;
    return marked
      .map((element, at) => ({ element, at }))
      .sort((a, b) => order(a.element) - order(b.element) || a.at - b.at)
      .map(({ element }) => {
        const asked = element.getAttribute("data-pinecall-do");
        const move: Line["do"] = asked === "highlight" || asked === "scroll_to" ? asked : "point";
        return { at: this.#ref(element), say: clean(element.getAttribute("data-pinecall-say"), 400), do: move };
      })
      .filter((line) => line.say !== "");
  }

  /** The ref the agent knows `element` by. */
  refOf(element: Element): string {
    return this.#ref(element);
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
   * The ref of what a person would mean by `name`, anywhere on the page, on the screen or not (a section
   * out of view is one line of the snapshot, and the things in it can still be named): the name said
   * exactly, else one that starts with it, else one that holds it, a section before a heading before
   * a card, a button or a link when several share it.
   */
  named(name: string): string | null {
    const wanted = name.trim().toLowerCase();
    if (wanted === "") return null;
    const candidates: { ref: string; role: string; name: string }[] = [];
    for (const element of this.#document.body.querySelectorAll("*")) {
      if (element.matches(IGNORED) || left(element)) continue;
      const role = roleOf(element);
      if (role === null || !POINTABLE.has(role)) continue;
      const said = nameOf(element, role).toLowerCase();
      if (said !== "") candidates.push({ ref: this.#ref(element), role, name: said });
    }
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
        const held = holds(child);
        const inside = held.length > 0 ? `, holds ${held.map((one) => `"${one}"`).join(", ")}` : "";
        const line = child.hasAttribute("data-pinecall-say") ? " [has a line]" : "";
        lines.push(`${indent}- region "${name}" [ref=${this.#ref(child)}] (${box.top > 0 ? "below" : "above"}${inside})${line}`);
        continue;
      }
      const kept = role !== null && (name !== "" || LANDMARKS.has(role));
      if (!kept) {
        const words = role === null && visible ? wordsIn(child) : "";
        if (words !== "") lines.push(`${indent}- text "${words.replaceAll('"', "'")}"`);
        else this.#walk(child, depth, height, lines);
        continue;
      }
      if (!visible && !FRAME.has(role)) continue;
      const parts = [`- ${role}`];
      if (name !== "") parts.push(`"${name.replaceAll('"', "'")}"`);
      if (role === "heading") parts.push(`[level=${child.tagName.slice(1)}]`);
      if (child instanceof HTMLDetailsElement) parts.push(child.open ? "[expanded]" : "[collapsed]");
      if (POINTABLE.has(role)) parts.push(`[ref=${this.#ref(child)}]`);
      parts.push(...heldBy(child));
      if (child.hasAttribute("data-pinecall-say")) parts.push("[has a line]");
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

/** How many of a section's things its one line names, when the section is out of view. */
const HELD_AT_MOST = 8;
const HELD = new Set(["heading", "article", "button", "link"]);

/** The things a section out of view holds, by name, so the agent knows what it can scroll to. */
function holds(region: Element): string[] {
  const names: string[] = [];
  for (const element of region.querySelectorAll("*")) {
    if (names.length >= HELD_AT_MOST) break;
    if (element.matches(IGNORED) || left(element)) continue;
    const role = roleOf(element);
    if (role === null || !HELD.has(role)) continue;
    const name = nameOf(element, role).replaceAll('"', "'");
    if (name !== "" && !names.includes(name)) names.push(name);
  }
  return names;
}

/** Out of the snapshot: hidden, marked by the site, or a secret. */
/** What a field holds now, as the visitor sees it: its value, the option chosen and the others, ticked or not. */
function heldBy(field: Element): string[] {
  const quoted = (text: string): string => `"${clean(text, 80).replaceAll('"', "'")}"`;
  if (field instanceof HTMLSelectElement) {
    const options = [...field.options].map((option) => quoted(option.text));
    const chosen = field.selectedOptions[0]?.text ?? "";
    return [chosen === "" ? "[empty]" : `[value=${quoted(chosen)}]`, `(options ${options.join(", ")})`];
  }
  if (field instanceof HTMLInputElement && (field.type === "checkbox" || field.type === "radio")) return [field.checked ? "[checked]" : "[unchecked]"];
  if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) return [field.value === "" ? "[empty]" : `[value=${quoted(field.value)}]`];
  return [];
}

/** The words of a box holding only words and inline marks, as `<div>$19<small> / month</small></div>`; none when it holds more. */
function wordsIn(box: Element): string {
  const inner = [...box.children];
  if (inner.some((child) => roleOf(child) !== null || child.children.length > 0)) return "";
  return clean([...box.childNodes].map((node) => (node instanceof Text || (node instanceof Element && !left(node)) ? node.textContent : "")).join(""), 120);
}

function left(element: Element): boolean {
  if (element.closest("[data-pinecall-skip], [aria-hidden='true']") !== null) return true;
  if (element instanceof HTMLInputElement && (element.type === "password" || element.autocomplete.startsWith("cc-"))) return true;
  const style = element.ownerDocument.defaultView?.getComputedStyle(element);
  return style !== undefined && (style.display === "none" || style.visibility === "hidden");
}
