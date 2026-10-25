/** A card beside the resting face for what the agent puts on the screen: the free times, a form, a piece of code. */
//
// It stands on the person's layer, above the face's corner, out of what the agent reads. The page
// draws what is in it (`show` hands it the body); the card keeps it until it is put away, replaced or
// the call ends. Colours: --pc-card and --pc-card-ink, else the bubble's.

const STYLE = `
.pc-card { position: fixed; z-index: 1; right: 22px; bottom: 112px; box-sizing: border-box; width: min(600px, calc(100vw - 32px));
  max-height: min(78vh, 720px); overflow: auto; padding: 20px 22px; border-radius: 16px; pointer-events: auto;
  background: var(--pc-card, var(--pc-bubble, #fff)); color: var(--pc-card-ink, var(--pc-bubble-ink, #17201c));
  border: 1px solid rgb(127 127 127 / .24); box-shadow: 0 18px 50px rgb(0 0 0 / .3);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; transform-origin: bottom right; transition: opacity .22s, transform .22s; }
.pc-card[hidden] { display: block !important; opacity: 0; transform: translateY(8px) scale(.98); pointer-events: none; }
.pc-layer.pc-left .pc-card { right: auto; left: 22px; transform-origin: bottom left; }
.pc-card-x { all: unset; position: absolute; top: 8px; right: 10px; width: 22px; height: 22px; line-height: 22px; text-align: center;
  border-radius: 50%; cursor: pointer; opacity: .5; font-size: 16px; }
.pc-card-x:hover, .pc-card-x:focus-visible { opacity: 1; background: rgb(127 127 127 / .2); }
@media (prefers-reduced-motion: reduce) { .pc-card { transition: none; } }
`;

export class Card {
  readonly #style: HTMLStyleElement;
  readonly #card: HTMLElement;
  readonly #body: HTMLElement;
  #cleanup: (() => void) | undefined;
  #fading: ReturnType<typeof setTimeout> | undefined;

  /** The card, hidden, put on a layer by `host`; `label` names its close button. */
  constructor(document: Document, host: (element: Element) => void, label: string) {
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    document.head.append(this.#style);
    this.#card = document.createElement("div");
    this.#card.className = "pc-card";
    this.#card.hidden = true;
    this.#card.setAttribute("role", "dialog");
    const close = document.createElement("button");
    close.type = "button";
    close.className = "pc-card-x";
    close.textContent = "×";
    close.setAttribute("aria-label", label);
    close.title = label;
    close.addEventListener("click", () => this.hide());
    this.#body = document.createElement("div");
    this.#card.append(this.#body, close);
    host(this.#card);
  }

  /** Put something on the card, in place of what it held: `render` draws into the body, and may answer how to take it down. */
  show(render: (body: HTMLElement) => void | (() => void)): void {
    this.#release();
    clearTimeout(this.#fading);
    this.#card.hidden = false;
    this.#cleanup = render(this.#body) ?? undefined;
  }

  /** Put it away. */
  hide(): void {
    if (this.#card.hidden) return;
    this.#card.hidden = true;
    // What it held goes once it has faded, unless something else was put on it meanwhile.
    this.#fading = setTimeout(() => this.#release(), 260);
  }

  get shown(): boolean {
    return !this.#card.hidden;
  }

  close(): void {
    clearTimeout(this.#fading);
    this.#release();
    this.#card.remove();
    this.#style.remove();
  }

  #release(): void {
    this.#cleanup?.();
    this.#cleanup = undefined;
    this.#body.replaceChildren();
  }
}
