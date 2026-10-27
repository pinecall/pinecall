/** A page's text as a person reads it: the words of an element, an output line by line, the line a note finds, and a text cut into recordings. */

import { isElement } from "../pointer/frames.js";

/** Under it nothing is read (code, a legend), though an example marked to press or type there is still done. */
export const QUIET_ATTRIBUTE = "data-pinecall-quiet";
/** The most characters one recording takes: a few sentences. */
const LONGEST = 480;

const INLINE = new Set(["SPAN", "CODE", "B", "I", "EM", "STRONG", "A", "SMALL", "KBD", "U", "S", "MARK", "TIME", "SUB", "SUP", "ABBR"]);

/** The nearest box of `element`, within `within`, that is a line of its own: not a run of words (a span, a code) inside one. */
export function blockOf(element: Element, within: Element): Element {
  let node = element;
  while (node !== within && node.parentElement !== null) {
    const display = node.ownerDocument.defaultView?.getComputedStyle(node).display ?? "";
    if (!INLINE.has(node.tagName) && !display.startsWith("inline") && display !== "contents") return node;
    node = node.parentElement;
  }
  return node;
}

/** What an output shows, line by line: each box of its own on a line, the words inside it as written. Hidden parts left out. */
export function textOf(output: Element): string {
  const lines: string[] = [];
  const walk = (node: Node, line: string[]): void => {
    for (const child of node.childNodes) {
      // By node type, not `instanceof`: a frame's nodes are of the frame's window.
      if (child.nodeType === 3) line.push(child.textContent ?? "");
      else if (isElement(child) && seen(child) && !child.matches("script, style, template")) {
        // A span laid out as a block (a cell of a row) is a line of its own; one in a run of words is not.
        const display = child.ownerDocument.defaultView?.getComputedStyle(child).display ?? "";
        const inline = display === "" ? INLINE.has(child.tagName) : display.startsWith("inline");
        if (inline) walk(child, line);
        else {
          const own: string[] = [];
          walk(child, own);
          lines.push(own.join("").replace(/\s+/g, " ").trim());
        }
      }
    }
  };
  const top: string[] = [];
  walk(output, top);
  const first = top.join("").replace(/\s+/g, " ").trim();
  return [first, ...lines].filter((line) => line !== "").join("\n");
}

/** A text as two are compared for a note: one space between words, in lower case. */
const flat = (text: string): string => text.replace(/\s+/g, " ").trim().toLowerCase();

/** The line of `output` that holds `find`, a text in any case and spacing or `/a regex/flags`: the innermost box that holds it; null when none does. */
export function lineIn(output: Element, find: string): Element | null {
  const expr = /^\/(.+)\/([a-z]*)$/.exec(find);
  let matches: (text: string) => boolean;
  try {
    const regex = expr === null ? null : new RegExp(expr[1] ?? "", (expr[2] ?? "").replace("g", ""));
    const wanted = flat(find);
    matches = regex === null ? (text) => flat(text).includes(wanted) : (text) => regex.test(text);
  } catch {
    return null;
  }
  const holding = [...output.querySelectorAll("*")].filter((element) => matches(element.textContent ?? ""));
  const innermost = holding.find((element) => !holding.some((other) => other !== element && element.contains(other)));
  if (innermost === undefined) return matches(output.textContent ?? "") ? output : null;
  return blockOf(innermost, output);
}

/** Whether a person sees `element`: not hidden, not left out for the tutor. */
export function seen(element: Element): boolean {
  if (element.closest("[hidden], [aria-hidden='true'], [data-pinecall-skip]") !== null) return false;
  const style = element.ownerDocument.defaultView?.getComputedStyle(element);
  return style === undefined || (style.display !== "none" && style.visibility !== "hidden");
}

/** The words a person reads out of `element`, on one line: its text, without what is quiet or hidden inside it. */
export function wordsOf(element: Element): string {
  const document = element.ownerDocument;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let text = "";
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (parent === null || parent.closest(`[${QUIET_ATTRIBUTE}]`) !== null || !seen(parent) || parent.matches("script, style, template")) continue;
    text += node.textContent ?? "";
  }
  return text.replace(/\s+/g, " ").trim();
}

/** A text as it is recorded: whole when it fits, else a few sentences at a time, `longest` characters at most each. */
export function piecesOf(text: string, longest = LONGEST): string[] {
  if (text.length <= longest) return text === "" ? [] : [text];
  const sentences = text.split(/(?<=[.!?…:;])\s+/);
  const pieces: string[] = [];
  let piece = "";
  for (const sentence of sentences.flatMap((one) => (one.length <= longest ? [one] : cut(one, longest)))) {
    if (piece !== "" && piece.length + 1 + sentence.length > longest) {
      pieces.push(piece);
      piece = sentence;
    } else piece = piece === "" ? sentence : `${piece} ${sentence}`;
  }
  if (piece !== "") pieces.push(piece);
  return pieces;
}

/** A sentence longer than a recording, cut between its words. */
function cut(sentence: string, longest: number): string[] {
  const pieces: string[] = [];
  let piece = "";
  for (const word of sentence.split(" ")) {
    if (piece !== "" && piece.length + 1 + word.length > longest) {
      pieces.push(piece);
      piece = word;
    } else piece = piece === "" ? word : `${piece} ${word}`;
  }
  return piece === "" ? pieces : [...pieces, piece];
}
