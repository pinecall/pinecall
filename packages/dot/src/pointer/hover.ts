/** Hover without a mouse: the site's `:hover` rules mirrored onto an attribute, set where the pointer is. */
//
// A script cannot move the real mouse, so `:hover` never matches under a drawn pointer. Every rule
// of the page's own style sheets that says `:hover` is copied with `[data-pc-hover]` in its place,
// and the attribute goes on the element under the tip and every ancestor, as a real hover does.
// `pointerenter` and `mouseenter` are sent too, for a site whose code listens for them.

/** The attribute a mirrored hover matches. */
const HOVERED = "data-pc-hover";

/** The pointer's look over an element: a hand on a link, an I-beam in a field, the arrow elsewhere. */
export type Kind = "arrow" | "hand" | "ibeam";

export class Hover {
  readonly #document: Document;
  readonly #mirror: HTMLStyleElement;
  #on: Element[] = [];

  constructor(document: Document) {
    this.#document = document;
    this.#mirror = document.createElement("style");
    this.#mirror.dataset["pinecallSkip"] = "";
    this.#mirror.textContent = mirrored(document);
    document.head.append(this.#mirror);
  }

  /** Hover what is at (x, y) in the viewport; the kind of pointer it asks for. */
  at(x: number, y: number): Kind {
    const under = this.#document.elementFromPoint(x, y);
    const chain: Element[] = [];
    for (let node = under; node !== null && node !== this.#document.body; node = node.parentElement) chain.push(node);
    for (const node of this.#on) if (!chain.includes(node)) left(node);
    for (const node of chain) if (!this.#on.includes(node)) entered(node);
    this.#on = chain;
    return under === null ? "arrow" : kindOf(under);
  }

  /** Hover nothing. */
  clear(): void {
    for (const node of this.#on) left(node);
    this.#on = [];
  }

  close(): void {
    this.clear();
    this.#mirror.remove();
  }
}

function entered(node: Element): void {
  node.setAttribute(HOVERED, "");
  node.dispatchEvent(new PointerEvent("pointerenter"));
  node.dispatchEvent(new MouseEvent("mouseenter"));
}

function left(node: Element): void {
  node.removeAttribute(HOVERED);
  node.dispatchEvent(new PointerEvent("pointerleave"));
  node.dispatchEvent(new MouseEvent("mouseleave"));
}

function kindOf(element: Element): Kind {
  const asked = element.ownerDocument.defaultView?.getComputedStyle(element).cursor ?? "auto";
  if (asked === "pointer") return "hand";
  if (asked === "text") return "ibeam";
  if (asked === "auto" && element.matches("input:not([type=checkbox]):not([type=radio]):not([type=range]), textarea, [contenteditable=true]")) return "ibeam";
  return "arrow";
}

/** Every `:hover` rule the page's sheets can be read for, rewritten. A sheet of another origin cannot be read, and is skipped. */
export function mirrored(document: Document): string {
  const out: string[] = [];
  const visit = (rules: CSSRuleList, wrap: (body: string) => string): void => {
    for (const rule of rules) {
      if (rule instanceof CSSMediaRule) visit(rule.cssRules, (body) => wrap(`@media ${rule.media.mediaText} { ${body} }`));
      else if (rule instanceof CSSStyleRule && rule.selectorText.includes(":hover")) {
        out.push(wrap(`${rule.selectorText.replaceAll(":hover", `[${HOVERED}]`)} { ${rule.style.cssText} }`));
      }
    }
  };
  for (const sheet of document.styleSheets) {
    let rules: CSSRuleList;
    try {
      rules = sheet.cssRules;
    } catch {
      continue;
    }
    visit(rules, (body) => body);
  }
  return out.join("\n");
}
