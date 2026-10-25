// The talking dot, <pinecall-widget look="dot">: the button is a face that speaks with the agent's
// voice, and a click is a voice call with no panel. With `tutor`, the dot is one more person on the
// page, with a pointer of its own. Loaded by the widget only for that look.
//
// It stands on @pinecall/room, which joins the call and reads its log straight from the gateway
// with the call's own token, and @pinecall/dot, whose face and tutor read the room. The widget
// around it mints the tokens, keeps the conversation in its history, and opens its menu when a
// call cannot start.

import { litAt, room, sayingOf } from "https://cdn.jsdelivr.net/npm/@pinecall/room@0.11/+esm";
import { face, tutor } from "https://cdn.jsdelivr.net/npm/@pinecall/dot@0.11/+esm";

// How long the agent's last line stays in the bubble after the reply closed, in ms.
const LINGER_MS = 2600;

const STYLE = `
  .fab.dot { width: var(--_dot); height: var(--_dot); padding: 0; border: 0; border-radius: 50%; background: none;
             box-shadow: none; --pc-face: var(--_accent); }
  .fab.dot .face { display: block; width: 100%; height: 100%; }
  :host { --_dot: var(--pc-dot-size, 64px); }
  :host([position="inline"]) { position: relative; }
  .dot-bubble { position: fixed; right: var(--_offset); bottom: calc(var(--_offset) + var(--_dot) + 10px); z-index: var(--_z);
                max-width: min(280px, calc(100vw - 2 * var(--_offset))); padding: 9px 13px; border: 1px solid var(--_line);
                border-radius: 16px 16px 4px 16px; background: var(--_surface); box-shadow: 0 8px 24px var(--_shadow); font-size: .93em; }
  .dot-bubble .coming { opacity: .4; }
  .dot-bubble button { all: unset; cursor: pointer; color: var(--_accent-ink); font-weight: 500; }
  .dot-hang { position: fixed; right: calc(var(--_offset) + var(--_dot) + 10px); bottom: calc(var(--_offset) + var(--_dot) / 2 - 17px);
              z-index: var(--_z); height: 34px; padding: 0 14px; border: 0; border-radius: 999px; background: var(--_failed);
              color: #fff; font-weight: 500; cursor: pointer; }
  :host([position="bottom-left"]) .dot-bubble { right: auto; left: var(--_offset); border-radius: 16px 16px 16px 4px; }
  :host([position="bottom-left"]) .dot-hang, :host([position="top-left"]) .dot-hang { right: auto; left: calc(var(--_offset) + var(--_dot) + 10px); }
  :host([position="top-right"]) .dot-bubble, :host([position="top-left"]) .dot-bubble { bottom: auto; top: calc(var(--_offset) + var(--_dot) + 10px); }
  :host([position="top-right"]) .dot-hang, :host([position="top-left"]) .dot-hang { bottom: auto; top: calc(var(--_offset) + var(--_dot) / 2 - 17px); }
  :host([position="top-left"]) .dot-bubble { right: auto; left: var(--_offset); }
  :host([position="inline"]) .dot-bubble { position: absolute; right: 0; bottom: calc(100% + 10px); }
  :host([position="inline"]) .dot-hang { position: absolute; right: calc(100% + 10px); bottom: calc(50% - 17px); }
  .dot-typing { display: inline-flex; gap: 4px; padding: 4px 0; }
  .dot-typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--_muted); animation: dot-hop 1s infinite ease-in-out; }
  .dot-typing i:nth-child(2) { animation-delay: .15s; } .dot-typing i:nth-child(3) { animation-delay: .3s; }
  @keyframes dot-hop { 0%, 60%, 100% { transform: none; opacity: .4; } 30% { transform: translateY(-3px); opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .dot-typing i { animation: none; opacity: .7; } }
`;

/** Where the agent published its walks, in the environment the `walks` attribute names (production unless `sandbox`). */
function walksUrl(widget) {
  const env = widget.getAttribute("walks") === "sandbox" ? "?env=sandbox" : "";
  return `${widget.gateway}/v1/agents/${encodeURIComponent(widget.agent)}/public/walks${env}`;
}

/** The dot of one widget: its face, its call, the bubble that says what the agent says, and its hang-up. */
export class Dot {
  constructor(widget) {
    this.widget = widget;
    const fab = widget.$(".fab");
    const label = fab.querySelector(".label")?.textContent ?? "";
    const host = document.createElement("span");
    host.className = "face";
    host.setAttribute("part", "button-face");
    fab.replaceChildren(host);
    fab.classList.add("dot");
    fab.setAttribute("aria-label", label);
    fab.title = label;

    const style = document.createElement("style");
    style.textContent = STYLE;
    this.bubble = document.createElement("div");
    this.bubble.className = "dot-bubble";
    this.bubble.setAttribute("part", "bubble");
    this.bubble.setAttribute("role", "status");
    this.bubble.hidden = true;
    this.hang = document.createElement("button");
    this.hang.className = "dot-hang";
    this.hang.type = "button";
    this.hang.textContent = widget.words.hangUp;
    this.hang.hidden = true;
    this.hang.addEventListener("click", () => {
      this.hang.hidden = true;
      void this.call.leave();
    });
    widget.shadowRoot.append(style, this.bubble, this.hang);

    this.call = room({
      tokens: (scope, resume) => widget.token(scope, resume ?? null),
      gateway: widget.gateway,
      // The tutor's moves are its own; a card or choices has nowhere to be drawn on a dot, so the
      // page hears it and does what it likes.
      onUi: (data) => {
        if (this.tutor?.take(data)) return;
        widget.dispatchEvent(new CustomEvent("pinecall:ui", { detail: data }));
      },
    });
    this.tutor = null;
    if (widget.hasAttribute("tutor")) {
      // The tutor's person is the button: it rests where the dot would, and carries what it says.
      // `.fab` sets its own display, which a `hidden` attribute does not override.
      fab.style.display = "none";
      this.tutor = tutor(this.call, {
        dock: (widget.getAttribute("position") ?? "").endsWith("left") ? "left" : "right",
        label,
        onClick: () => this.click(),
        captions: widget.getAttribute("captions") ?? "both",
        shape: widget.getAttribute("shape") ?? undefined,
        color: widget.getAttribute("color") ?? undefined,
        words: { hangUp: widget.words.hangUp, captions: widget.words.captions, walks: widget.words.walks, stop: widget.words.stop, pause: widget.words.pause },
        // `walks` plays the agent's recorded walks with no call; `walks="sandbox"` reads the sandbox's.
        walks: widget.hasAttribute("walks") ? walksUrl(widget) : undefined,
        onWalk: (walked) => widget.dispatchEvent(new CustomEvent("pinecall:walk", { detail: walked })),
      });
      this.face = this.tutor;
    } else {
      this.face = face(host, this.call, { shape: widget.getAttribute("shape") ?? undefined, color: widget.getAttribute("color") ?? undefined });
      fab.style.visibility = "";
    }
    this.kept = null;
    this.turns = 0;
    this.shown = "";
    this.speech = null;
    this.last = { text: "", at: 0 };
    this.unsubscribe = this.call.subscribe((state) => this.heard(state));
    const paint = (at) => {
      this.paint(at);
      this.frame = requestAnimationFrame(paint);
    };
    this.frame = requestAnimationFrame(paint);
  }

  /** The dot was clicked: start a call, or during one, offer to hang up (the tutor has its own button). */
  click() {
    const { phase } = this.call.state;
    if (phase === "opening" || phase === "live") {
      if (!this.tutor) this.hang.hidden = !this.hang.hidden;
      return;
    }
    // Inside the click: a browser starts audio only here.
    this.face.wake();
    void this.start();
  }

  async start() {
    await this.call.start("talk");
    const { phase, error } = this.call.state;
    if (phase !== "failed") return;
    // A refused microphone, a token refused: the widget's menu, with the reason, and the chat in it.
    this.widget.toggle();
    this.widget.notice(error);
  }

  /** Each state the room publishes: the conversation kept as it goes, and kept closed when it ends. */
  heard(state) {
    if (state.phase === "live" && state.call && this.kept !== state.call) {
      this.kept = state.call;
      this.turns = 0;
      this.widget.began(state.call, "talk", state.resume || null);
      this.widget.dispatchEvent(new CustomEvent("pinecall:started", { detail: { call: state.call, scope: "talk" } }));
    }
    if (this.kept !== null) {
      for (; this.turns < state.log.turns.length; this.turns += 1) {
        const turn = state.log.turns[this.turns];
        this.widget.kept_line(`turn_${this.turns}`, turn.role === "user" ? "user" : "agent", turn.text);
      }
    }
    if ((state.phase === "ended" || state.phase === "failed") && this.kept !== null) {
      this.widget.ended();
      this.widget.dispatchEvent(new CustomEvent("pinecall:ended", { detail: { call: this.kept } }));
      this.kept = null;
    }
    if (state.phase !== "opening" && state.phase !== "live") this.hang.hidden = true;
  }

  /** The bubble, once a frame: the reply lit word by word as the voice says it, then held a moment. */
  paint(at) {
    const state = this.call.state;
    if (this.tutor && !state.wantsSound) {
      if (this.shown !== "") {
        this.shown = "";
        this.bubble.hidden = true;
      }
      return;
    }
    const saying = sayingOf(state.entries);
    if (saying !== null && this.speech?.id !== saying.speech) this.speech = { id: saying.speech, at };
    let shown = "";
    if (state.wantsSound) {
      shown = "sound";
    } else if (saying !== null && saying.words.length > 0) {
      const split = litAt(saying, at - this.speech.at);
      this.last = { text: split.lit + split.coming, at };
      shown = `say:${split.lit}\u0000${split.coming}`;
    } else if (state.phase === "opening" || (state.phase === "live" && state.log.agent_state === "thinking")) {
      shown = "typing";
    } else if (this.last.text && at - this.last.at < LINGER_MS) {
      shown = `say:${this.last.text}\u0000`;
    }
    if (shown === this.shown) return;
    this.shown = shown;
    this.bubble.hidden = shown === "";
    if (shown === "sound") {
      const ask = document.createElement("button");
      ask.type = "button";
      ask.textContent = this.widget.words.tapToHear;
      ask.addEventListener("click", () => this.call.playSound());
      this.bubble.replaceChildren(ask);
    } else if (shown === "typing") {
      const typing = document.createElement("span");
      typing.className = "dot-typing";
      typing.setAttribute("aria-label", this.widget.words.connecting);
      typing.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
      this.bubble.replaceChildren(typing);
    } else if (shown.startsWith("say:")) {
      const [lit, coming] = shown.slice(4).split("\u0000");
      const later = document.createElement("span");
      later.className = "coming";
      later.textContent = coming;
      this.bubble.replaceChildren(document.createTextNode(lit), later);
    }
  }

  /** Tell the agent what the visitor did on the page. */
  event(name, data) {
    return this.call.event(name, data);
  }

  /** The tag left the page: like a reload, not a hang-up, so the call waits for the visitor. */
  close() {
    cancelAnimationFrame(this.frame);
    this.unsubscribe();
    this.face.close();
    this.call.close();
  }
}
