/** A window of code the tutor opens beside the page while it explains it, the lines it talks about lit. */
//
// It stands on the person's layer, out of what the agent reads, at the page's left edge, centred in
// the height, so the pointer and the page stay in sight. The lines lit are the ones the voice is on;
// the rest dim, and the lit ones are scrolled into the window. Colours: --pc-face, and the window's own.

import type { CodeView } from "../wire/index.js";

const STYLE = `
.pc-code { position: fixed; left: 24px; top: 50%; width: min(460px, calc(100vw - 48px)); max-height: min(70vh, 520px);
  display: flex; flex-direction: column; transform: translateY(-50%); border-radius: 14px; overflow: hidden; pointer-events: auto;
  background: #14151f; color: #e6e6f0; box-shadow: 0 24px 60px rgb(0 0 0 / .35), 0 0 0 1px rgb(255 255 255 / .06);
  transition: opacity .25s, transform .25s; font: 13px/1.6 ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.pc-code[hidden] { display: flex !important; opacity: 0; transform: translateY(-46%); pointer-events: none; }
.pc-code-bar { display: flex; align-items: center; gap: 7px; padding: 10px 14px; background: #1b1c29; font-size: 12px; color: #a3a3b8; }
.pc-code-bar i { width: 10px; height: 10px; border-radius: 50%; background: #3a3b4d; }
.pc-code-bar span { margin-left: 6px; }
.pc-code-lines { margin: 0; padding: 12px 0; overflow: auto; }
.pc-code-line { display: flex; padding: 0 16px 0 0; transition: opacity .2s, background-color .2s; white-space: pre; }
.pc-code-line b { flex: none; width: 3.2em; padding-right: 1em; text-align: right; font-weight: 400; color: #5d5e75; user-select: none; }
.pc-code.pc-lit .pc-code-line { opacity: .42; }
.pc-code.pc-lit .pc-code-line.pc-on { opacity: 1; background: color-mix(in srgb, var(--pc-face, #1f6b55) 22%, transparent);
  box-shadow: inset 3px 0 var(--pc-face, #1f6b55); }
@media (max-width: 720px) { .pc-code { top: auto; bottom: 120px; transform: none; max-height: 45vh; } .pc-code[hidden] { transform: translateY(8px); } }
@media (prefers-reduced-motion: reduce) { .pc-code, .pc-code-line { transition: none; } }
`;

export class CodeWindow {
  readonly #document: Document;
  readonly #style: HTMLStyleElement;
  readonly #window: HTMLElement;
  readonly #title: HTMLElement;
  readonly #lines: HTMLElement;
  #shown: CodeView | null = null;

  /** The window, hidden, put on a layer by `host`. */
  constructor(document: Document, host: (element: Element) => void) {
    this.#document = document;
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    document.head.append(this.#style);
    this.#window = document.createElement("div");
    this.#window.className = "pc-code";
    this.#window.hidden = true;
    this.#window.setAttribute("role", "figure");
    this.#window.innerHTML = `<div class="pc-code-bar"><i></i><i></i><i></i><span></span></div><pre class="pc-code-lines"></pre>`;
    this.#title = this.#window.querySelector("span") ?? this.#window;
    this.#lines = this.#window.querySelector("pre") ?? this.#window;
    host(this.#window);
  }

  /** What a step shows: a window opened (or another in its place), closed with `null`, and the lines lit. */
  show(code: CodeView | null | undefined, lines: [number, number] | undefined): void {
    if (code === null) return this.hide();
    if (code !== undefined && code !== this.#shown) this.#open(code);
    if (lines !== undefined) this.light(lines);
  }

  /** Light lines `from` to `to` (from 1), dim the rest, and bring the lit ones into the window. */
  light([from, to]: [number, number]): void {
    if (this.#shown === null) return;
    this.#window.classList.add("pc-lit");
    const rows = [...this.#lines.children];
    rows.forEach((row, at) => row.classList.toggle("pc-on", at + 1 >= from && at + 1 <= to));
    rows[from - 1]?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  /** Whether a window is open. */
  get open(): boolean {
    return this.#shown !== null;
  }

  hide(): void {
    this.#shown = null;
    this.#window.hidden = true;
  }

  close(): void {
    this.#window.remove();
    this.#style.remove();
  }

  #open(code: CodeView): void {
    this.#shown = code;
    this.#title.textContent = code.title;
    this.#window.classList.remove("pc-lit");
    this.#lines.replaceChildren(
      ...code.text.split("\n").map((text, at) => {
        const row = this.#document.createElement("div");
        row.className = "pc-code-line";
        const number = this.#document.createElement("b");
        number.textContent = String(at + 1);
        row.append(number, this.#document.createTextNode(text === "" ? " " : text));
        return row;
      }),
    );
    this.#window.hidden = false;
  }
}
