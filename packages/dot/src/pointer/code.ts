/** A window of code the tutor opens beside the page while it explains it: written in line by line, coloured, the lines it talks about lit. */
//
// It stands on the person's layer, out of what the agent reads, at the page's left, centred in the
// height, so the pointer and the page stay in sight. As it opens its lines come in one after another,
// as if written; the lines lit are the ones the voice is on, the rest dim, and `show` answers the
// first lit line, for the pointer to go to. Colours: --pc-face, and the window's own.

import type { CodeView } from "../wire/index.js";
import { coloured } from "./syntax.js";

/** How long one line takes to come in as the window opens, in ms. */
const LINE_MS = 55;

const STYLE = `
.pc-code { position: fixed; left: 32px; top: 50%; width: min(640px, calc(100vw - 64px)); max-height: min(80vh, 640px);
  display: flex; flex-direction: column; transform: translateY(-50%); border-radius: 16px; overflow: hidden; pointer-events: auto;
  background: #11121b; color: #e4e4f0; box-shadow: 0 30px 80px rgb(0 0 0 / .45), 0 0 0 1px rgb(255 255 255 / .07);
  transition: opacity .3s, transform .3s; font: 14px/1.7 ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace; }
.pc-code[hidden] { display: flex !important; opacity: 0; transform: translateY(-47%) scale(.98); pointer-events: none; }
.pc-code-bar { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #181927; font-size: 12.5px; color: #9b9bb4;
  border-bottom: 1px solid rgb(255 255 255 / .05); }
.pc-code-bar i { width: 11px; height: 11px; border-radius: 50%; background: #34354a; }
.pc-code-bar span { margin-left: 8px; }
.pc-code-lines { margin: 0; padding: 14px 0; overflow: auto; }
.pc-code-line { display: flex; padding: 0 20px 0 0; white-space: pre; transition: opacity .25s, background-color .25s, box-shadow .25s; }
.pc-code-line b { flex: none; width: 3.4em; padding-right: 1.2em; text-align: right; font-weight: 400; color: #4f5068; user-select: none; }
.pc-code-line.pc-coming { opacity: 0; transform: translateX(-4px); }
.pc-code-line:not(.pc-coming) { transition: opacity .25s, transform .25s, background-color .25s, box-shadow .25s; }
.pc-code.pc-lit .pc-code-line:not(.pc-coming) { opacity: .38; }
.pc-code.pc-lit .pc-code-line.pc-on { opacity: 1; background: color-mix(in srgb, var(--pc-face, #b7a6ff) 20%, transparent);
  box-shadow: inset 3px 0 var(--pc-face, #b7a6ff); }
.pc-k-comment { color: #7b7f9e; font-style: italic; } .pc-k-keyword { color: #c792ea; } .pc-k-string { color: #c3e88d; }
.pc-k-decorator { color: #ffcb6b; } .pc-k-type { color: #82aaff; } .pc-k-tag { color: #f07178; } .pc-k-number { color: #f78c6c; }
.pc-k-self { color: #ff9cac; }
@media (max-width: 720px) { .pc-code { left: 12px; width: calc(100vw - 24px); top: auto; bottom: 120px; transform: none; max-height: 48vh; font-size: 12.5px; }
  .pc-code[hidden] { transform: translateY(8px); } }
@media (prefers-reduced-motion: reduce) { .pc-code, .pc-code-line { transition: none; } }
`;

export class CodeWindow {
  readonly #document: Document;
  readonly #style: HTMLStyleElement;
  readonly #window: HTMLElement;
  readonly #title: HTMLElement;
  readonly #lines: HTMLElement;
  readonly #still: boolean;
  #shown: CodeView | null = null;
  #writing: ReturnType<typeof setTimeout>[] = [];

  /** The window, hidden, put on a layer by `host`; `still` writes its lines in at once (reduced motion). */
  constructor(document: Document, host: (element: Element) => void, still = false) {
    this.#document = document;
    this.#still = still;
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

  /**
   * What a step shows: a window opened (or another in its place) for `code`, closed for `null`, kept as
   * it is for none; and `lines` lit. Answers the first lit line, for the pointer to go to.
   */
  show(code: CodeView | null | undefined, lines: [number, number] | undefined): HTMLElement | null {
    if (code === null) {
      this.hide();
      return null;
    }
    if (code !== undefined && code !== this.#shown) this.#open(code);
    return lines === undefined ? null : this.light(lines);
  }

  /** Light lines `from` to `to` (from 1), dim the rest, bring the lit ones into the window; answers the first one's code, past its number. */
  light([from, to]: [number, number]): HTMLElement | null {
    if (this.#shown === null) return null;
    this.#window.classList.add("pc-lit");
    const rows = [...this.#lines.children];
    rows.forEach((row, at) => row.classList.toggle("pc-on", at + 1 >= from && at + 1 <= to));
    const first = rows[from - 1];
    first?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    const code = [...(first?.querySelectorAll("span") ?? [])].find((span) => (span.textContent ?? "").trim() !== "");
    return code ?? (first instanceof HTMLElement ? first : null);
  }

  /** Whether a window is open. */
  get open(): boolean {
    return this.#shown !== null;
  }

  hide(): void {
    this.#stopWriting();
    this.#shown = null;
    this.#window.hidden = true;
  }

  close(): void {
    this.#stopWriting();
    this.#window.remove();
    this.#style.remove();
  }

  #open(code: CodeView): void {
    this.#stopWriting();
    this.#shown = code;
    this.#title.textContent = code.title;
    this.#window.classList.remove("pc-lit");
    const rows = coloured(code.text).map((pieces, at) => {
      const row = this.#document.createElement("div");
      row.className = this.#still ? "pc-code-line" : "pc-code-line pc-coming";
      const number = this.#document.createElement("b");
      number.textContent = String(at + 1);
      row.append(number);
      for (const piece of pieces) {
        const span = this.#document.createElement("span");
        if (piece.kind !== "plain") span.className = `pc-k-${piece.kind}`;
        span.textContent = piece.text;
        row.append(span);
      }
      if (pieces.length === 0) row.append(this.#document.createTextNode(" "));
      return row;
    });
    this.#lines.replaceChildren(...rows);
    this.#window.hidden = false;
    this.#writing = rows.map((row, at) => setTimeout(() => row.classList.remove("pc-coming"), this.#still ? 0 : (at + 1) * LINE_MS));
  }

  #stopWriting(): void {
    for (const timer of this.#writing) clearTimeout(timer);
    this.#writing = [];
  }
}
