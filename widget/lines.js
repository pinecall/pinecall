// The conversation on <pinecall-widget>'s screen: the lines as they arrive, the three dots while the
// agent thinks, its words typed out at a reading pace, and what it shows held until they are read.

import { deal } from "./cards.js";
import { said } from "./markup.js";

const SEGMENT_ID = "lk.segment_id";
const TRANSCRIPTION_FINAL = "lk.transcription_final";
// The agent's words arrive in a burst of a few hundred milliseconds, which reads as nothing: they are
// typed out instead, character by character on the animation frame, at this many a second.
const REVEAL_CPS = 80;
// On a voice call, what the agent shows comes this long after it starts speaking.
const VOICE_SHOWS_AFTER_MS = 1200;
// An answer with no words at all: after this long the dots go, and whatever it showed is shown.
const WORDLESS_AFTER_MS = 15000;

export class Lines {
  constructor(widget) {
    this.widget = widget;
    this.list = widget.$(".lines");
    // Each line on screen by its segment, so its later chunks land in it.
    this.streams = new Map();
    // The order of an answer: her line, the dots, the agent's words at a reading pace, then what it shows.
    this.typing = null;
    this.reveals = new Map();
    // Segments shown whole the moment they arrive, in place of the greeting stand-in.
    this.instant = new Set();
    this.frame = null;
    this.early = null;
    this.shelved = [];
  }

  /** Nothing on screen: a conversation starts over. */
  clear() {
    this.list.replaceChildren();
    this.streams.clear();
    this.settled();
    this.reveals.clear();
    this.instant.clear();
    clearTimeout(this.early);
    this.early = null;
    cancelAnimationFrame(this.frame);
    this.frame = null;
    this.shelved = [];
  }

  /** A new room: its segments are its own. */
  forgetStreams() {
    this.streams.clear();
  }

  get empty() {
    return this.list.childElementCount === 0;
  }

  scroll() {
    this.list.scrollTop = this.list.scrollHeight;
  }

  /** The lines of a conversation kept, as they were said. */
  drawKept(lines) {
    for (const line of lines) {
      const item = document.createElement("li");
      item.className = line.who === "user" ? "user" : "agent";
      if (line.who === "user") item.textContent = line.text;
      else item.replaceChildren(said(line.text));
      this.list.append(item);
    }
    this.scroll();
  }

  /** The page's greeting, standing in until the agent's own first words replace it. */
  hello(greeting) {
    const hello = document.createElement("li");
    hello.className = "agent hello";
    hello.textContent = greeting;
    this.list.append(hello);
  }

  /** One text stream of the room: the visitor's words or the agent's, drawn as they come. */
  async read(reader, identity) {
    const widget = this.widget;
    const id = reader.info.attributes?.[SEGMENT_ID] ?? reader.info.id;
    // Whatever this browser did not send is the agent's: its first words can land before it is listed as a participant.
    const who = identity === widget.room?.localParticipant.identity ? "user" : "agent";
    // The agent's greeting opens every call. In place of the page's stand-in it is shown at once, not
    // typed; on a call that follows one that ended mid-conversation it is held back and, when it is
    // indeed the greeting, dropped: the conversation on screen is one.
    let quiet = false;
    if (who === "agent") {
      widget.onArrived?.();
      const standIn = this.list.querySelector(".hello");
      if (standIn) {
        // The stand-in becomes the greeting's own line: nothing disappears, nothing is typed again.
        standIn.className = "agent";
        this.streams.set(id, standIn);
        this.instant.add(id);
      } else if (widget.greeting && this.list.querySelector("li.agent:not(.typing)")) quiet = true;
    }
    let text = "";
    for await (const chunk of reader) {
      text += chunk;
      if (quiet && widget.greeting.startsWith(text)) continue;
      quiet = false;
      this.draw(id, who, text, false);
    }
    if (quiet && text === widget.greeting) return;
    this.draw(id, who, text, reader.info.attributes?.[TRANSCRIPTION_FINAL] === "true");
  }

  draw(id, who, text, final) {
    let line = this.streams.get(id);
    if (!line) {
      line = document.createElement("li");
      this.streams.set(id, line);
      // The agent's first word takes the place of the dots.
      if (who.startsWith("agent")) this.settled();
      this.list.append(line);
    }
    if (who.startsWith("agent")) return this.reveal(id, line, text, final);
    line.className = `${who}${final ? "" : " interim"}`;
    line.textContent = text;
    this.scroll();
    if (final) {
      this.widget.keptLine(id, "user", text);
      this.waiting();
    }
  }

  /** A line of hers that could not be sent leaves the screen. */
  drop(id) {
    this.streams.get(id)?.remove();
    this.streams.delete(id);
  }

  /** Three dots where the answer will be, from her line until the agent's first word. */
  waiting() {
    if (this.typing) return;
    const dots = document.createElement("li");
    dots.className = "agent typing";
    dots.setAttribute("aria-label", this.widget.words.typing);
    dots.append(...[0, 1, 2].map(() => document.createElement("i")));
    this.list.append(dots);
    this.scroll();
    this.typing = dots;
    this.typingTimer = setTimeout(() => this.settled(true), WORDLESS_AFTER_MS);
  }

  settled(timedOut = false) {
    clearTimeout(this.typingTimer);
    this.typing?.remove();
    this.typing = null;
    if (timedOut) this.unshelve(true);
  }

  /** The agent's words typed out at a reading pace; what has not arrived yet is never shown. */
  reveal(id, line, text, final) {
    let reveal = this.reveals.get(id);
    if (!reveal) {
      reveal = { line, target: "", shown: 0, final: false, at: 0, budget: 0, instant: this.instant.delete(id) };
      this.reveals.set(id, reveal);
      line.className = "agent interim";
    }
    reveal.target = text;
    reveal.final = final;
    if (reveal.instant) return this.revealStep(id, reveal, text.length);
    this.animate();
  }

  /** One animation frame loop for every line revealing: each gets the characters its elapsed time buys. */
  animate() {
    if (this.frame) return;
    const step = (now) => {
      this.frame = null;
      for (const [id, reveal] of this.reveals) {
        reveal.budget += ((now - (reveal.at || now)) * REVEAL_CPS) / 1000;
        reveal.at = now;
        const chars = Math.floor(reveal.budget);
        if (chars < 1) continue;
        reveal.budget -= chars;
        this.revealStep(id, reveal, chars);
      }
      if (this.reveals.size) this.frame = requestAnimationFrame(step);
    };
    this.frame = requestAnimationFrame(step);
  }

  revealStep(id, reveal, chars) {
    const widget = this.widget;
    const { target } = reveal;
    if (reveal.shown < target.length) {
      reveal.shown = Math.min(target.length, reveal.shown + chars);
      let visible = target.slice(0, reveal.shown);
      // A bold still open: closed for now when its end has arrived, held back whole when it has not.
      if (visible.split("**").length % 2 === 0) {
        if (target.indexOf("**", reveal.shown) !== -1 || reveal.final) visible += "**";
        else visible = visible.slice(0, visible.lastIndexOf("**"));
      }
      // The agent's line is read as the little Markdown it writes.
      reveal.line.replaceChildren(said(visible));
      // On a voice call the words come at the pace she hears them: what the agent shows comes a moment
      // after it starts speaking, not at the end of the sentence.
      if (widget.scope === "talk" && this.shelved.length && !this.early) {
        this.early = setTimeout(() => {
          this.early = null;
          this.unshelve(true);
        }, VOICE_SHOWS_AFTER_MS);
      }
      this.scroll();
      widget.peek(target.replace(/\*\*/g, ""));
    }
    if (reveal.final && reveal.shown >= target.length) {
      this.reveals.delete(id);
      reveal.line.className = "agent";
      reveal.line.replaceChildren(said(target));
      widget.keptLine(id, "agent", target);
      this.unshelve();
    }
  }

  /** What the agent shows waits for its words: the answer is read first, then what it put on screen. */
  shelve(item) {
    if (!this.typing && !this.reveals.size) {
      this.list.append(item);
      this.scroll();
      deal(item);
      return;
    }
    // A newer shelf of products in the same answer replaces the one waiting: the answer names the last one.
    if (item.classList.contains("products")) this.shelved = this.shelved.filter((other) => !other.classList.contains("products"));
    this.shelved.push(item);
  }

  unshelve(force = false) {
    if (!force && (this.reveals.size || this.typing)) return;
    const items = this.shelved.splice(0);
    for (const item of items) this.list.append(item);
    this.scroll();
    for (const item of items) deal(item);
    if (items.some((item) => item.classList.contains("products"))) this.widget.lowerKeyboard();
  }
}
