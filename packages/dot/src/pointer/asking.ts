/** The field in the walks' menu where the visitor types what they want shown: "where do I see what each plan includes?". */
//
// It stands above the menu's pills while the menu is open, and sends what was typed on Enter. Under it a
// line can say what came of it ("That one is a question for the agent") with one button, to take it on.
// It never answers in words of its own: the tutor does a thing on the page, or offers the agent.
// Colours: --pc-bubble, --pc-bubble-ink, --pc-face.

const STYLE = `
.pc-ask { position: fixed; z-index: 3; display: flex; flex-direction: column; gap: 6px; width: min(270px, calc(100vw - 32px)); pointer-events: auto; }
.pc-ask[hidden] { display: none; }
.pc-ask input { all: unset; box-sizing: border-box; width: 100%; height: 32px; padding: 0 14px; border-radius: 999px;
  background: var(--pc-bubble, #fff); color: var(--pc-bubble-ink, #17201c); font: 500 13px/32px system-ui, -apple-system, "Segoe UI", sans-serif;
  box-shadow: 0 4px 14px rgb(0 0 0 / .18), 0 0 0 1px color-mix(in srgb, var(--pc-face, #1f6b55) 35%, transparent); }
.pc-ask input:focus-visible { box-shadow: 0 4px 14px rgb(0 0 0 / .18), 0 0 0 2px var(--pc-face, #1f6b55); }
.pc-ask-hint { display: flex; align-items: center; gap: 8px; padding: 8px 10px 8px 12px; border-radius: 14px; background: var(--pc-bubble, #fff);
  color: var(--pc-bubble-ink, #17201c); font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; box-shadow: 0 4px 14px rgb(0 0 0 / .18); }
.pc-ask-hint[hidden] { display: none; }
.pc-ask-hint span { flex: 1; }
.pc-ask-hint button { all: unset; flex: none; padding: 5px 10px; border-radius: 999px; cursor: pointer; font-weight: 600; font-size: 12px;
  background: var(--pc-face, #1f6b55); color: #fff; }
.pc-ask-hint button[hidden] { display: none; }
.pc-ask-hint button:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
`;

export interface AskingOptions {
  /** The field's placeholder: "Ask me to show you…". */
  placeholder: string;
  /** What was typed, sent. */
  onAsk: (text: string) => void;
}

export class Asking {
  /** The field and its line, for the menu to place and to keep its clicks inside. */
  readonly element: HTMLFormElement;
  readonly #style: HTMLStyleElement;
  readonly #input: HTMLInputElement;
  readonly #hint: HTMLElement;
  readonly #said: HTMLElement;
  readonly #act: HTMLButtonElement;
  #action: (() => void) | null = null;

  constructor(document: Document, host: (element: Element) => void, options: AskingOptions) {
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    document.head.append(this.#style);
    this.element = document.createElement("form");
    this.element.className = "pc-ask";
    this.element.hidden = true;
    this.element.innerHTML = `<div class="pc-ask-hint" role="status" hidden><span></span><button type="button" hidden></button></div><input type="text" maxlength="300" autocomplete="off">`;
    this.#input = this.element.querySelector("input") ?? document.createElement("input");
    this.#input.placeholder = options.placeholder;
    this.#input.setAttribute("aria-label", options.placeholder);
    this.#hint = this.element.querySelector(".pc-ask-hint") ?? document.createElement("div");
    this.#said = this.#hint.querySelector("span") ?? document.createElement("span");
    this.#act = this.#hint.querySelector("button") ?? document.createElement("button");
    this.#act.addEventListener("click", () => this.#action?.());
    this.element.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = this.#input.value.trim();
      if (text === "") return;
      this.#input.value = "";
      this.hint(null);
      options.onAsk(text);
    });
    host(this.element);
  }

  /** Shown with the menu, or not. */
  show(on: boolean): void {
    this.element.hidden = !on;
  }

  /** Stand with its bottom `bottom` px above the window's bottom edge, its end `edge` px in from the side the face rests on. */
  place(bottom: number, edge: number, right: boolean): void {
    Object.assign(this.element.style, { bottom: `${bottom}px`, right: right ? `${edge}px` : "auto", left: right ? "auto" : `${edge}px` });
  }

  /** A line under the field about what was asked, with one button; null takes it away. */
  hint(text: string | null, action?: { label: string; onClick: () => void }): void {
    this.#hint.hidden = text === null;
    this.#said.textContent = text ?? "";
    this.#act.hidden = action === undefined;
    this.#act.textContent = action?.label ?? "";
    this.#action = action?.onClick ?? null;
  }

  focus(): void {
    this.#input.focus();
  }

  close(): void {
    this.element.remove();
    this.#style.remove();
  }
}
