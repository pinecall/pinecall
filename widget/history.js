// The visitor's conversations with one agent, kept in this browser alone, and the layer that lists
// them: the conversation under way is carried on after a page change or a reload, and the ones
// before it are read again under "Your conversations", carried on, deleted, or cleared.
// `history="off"` keeps none of them.

import { ICONS, said, when } from "./markup.js";

// How many conversations are kept, and how many lines of each.
const KEPT_AT_MOST = 20;
const LINES_AT_MOST = 200;

export class Kept {
  constructor(agent, on) {
    this.key = `pinecall-widget:conversations:${agent}`;
    this.on = on;
  }

  /** Every conversation kept, the newest first. */
  all() {
    if (!this.on) return [];
    try {
      const all = JSON.parse(localStorage.getItem(this.key) ?? "[]");
      return Array.isArray(all) ? all : [];
    } catch {
      return [];
    }
  }

  /** The conversation that was under way when the page last had it: the newest, unless it ended. */
  current() {
    const [newest] = this.all();
    return newest && newest.ended_at === null ? newest : null;
  }

  write(list) {
    if (!this.on) return;
    try {
      localStorage.setItem(this.key, JSON.stringify(list.slice(0, KEPT_AT_MOST)));
    } catch {
      // storage unavailable: the conversation lives for this page alone
    }
  }

  /** One conversation on top, in place of itself and of the calls it carries on (`replaces`). */
  put(one, replaces = []) {
    if (one.lines.length > LINES_AT_MOST) one.lines.splice(0, one.lines.length - LINES_AT_MOST);
    const gone = new Set([one.call, ...replaces]);
    this.write([one, ...this.all().filter((other) => !gone.has(other.call))]);
  }

  remove(call) {
    this.write(this.all().filter((one) => one.call !== call));
  }

  /** Every conversation forgotten but `keeping`, the one under way. */
  clear(keeping) {
    this.write(keeping ? [keeping] : []);
  }
}

/** What a kept conversation is called in a list: the first thing she said, else what it was. */
function title(one, words) {
  const first = one.lines.find((line) => line.who === "user") ?? one.lines[0];
  return first?.text ?? (one.scope === "talk" ? words.aCall : words.aChat);
}

/** "Your conversations": the ones before the one under way, the newest first; a tap reads one again. */
export function listKept(widget) {
  const words = widget.words;
  const past = widget.past();
  const layer = widget.layer(words.history);
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "clear";
  clear.textContent = words.clear;
  clear.addEventListener("click", () => {
    widget.forgetAll();
    widget.closeLayer();
  });
  layer.querySelector(".layer-bar").append(clear);
  const list = document.createElement("div");
  list.className = "kept";
  for (const one of past) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "kept-row";
    row.innerHTML = `<i>${one.scope === "talk" ? ICONS.phone : ICONS.chat}</i><span class="kept-words"><span class="kept-text"></span><span class="kept-when"></span></span>`;
    row.querySelector(".kept-text").textContent = title(one, words);
    row.querySelector(".kept-when").textContent = `${one.scope === "talk" ? words.callWord : words.chatWord} · ${when(one.started_at, words)}`;
    row.addEventListener("click", () => readKept(widget, one));
    list.append(row);
  }
  layer.querySelector(".layer-body").append(list);
}

/** One kept conversation read again, as it was said; one the gateway gave a resume token can be carried on. */
function readKept(widget, one) {
  const words = widget.words;
  const started = new Date(one.started_at);
  const date = `${started.toLocaleDateString(undefined, { day: "numeric", month: "short" })}, ${started.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`;
  const name = `${one.scope === "talk" ? words.callWord : words.chatWord} · ${date}${one.ended_at === null ? "" : ` · ${words.endedWord}`}`;
  const layer = widget.layer(name, () => listKept(widget));
  const forget = document.createElement("button");
  forget.type = "button";
  forget.className = "tool forget";
  forget.title = forget.ariaLabel = words.forget;
  forget.innerHTML = ICONS.trash;
  forget.addEventListener("click", () => {
    widget.kept.remove(one.call);
    widget.keptChanged();
    if (widget.past().length) listKept(widget);
    else widget.closeLayer();
  });
  layer.querySelector(".layer-bar").append(forget);
  const body = layer.querySelector(".layer-body");
  const lines = document.createElement("ul");
  lines.className = "lines";
  for (const line of one.lines) {
    const item = document.createElement("li");
    item.className = line.who === "user" ? "user" : "agent";
    if (line.who === "user") item.textContent = line.text;
    else item.replaceChildren(said(line.text));
    lines.append(item);
  }
  body.append(lines);
  if (one.resume) {
    const carry = document.createElement("button");
    carry.type = "button";
    carry.className = "pill";
    carry.textContent = words.carryOn;
    carry.addEventListener("click", () => void widget.carryOn(one));
    body.append(carry);
  }
  body.scrollTop = body.scrollHeight;
}
