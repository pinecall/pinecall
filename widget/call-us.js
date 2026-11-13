// "Call us" in <pinecall-widget>: the visitor calls the agent from their own phone, and the call shows
// up live in the panel.
//
// With `code-url` (or `codeProvider`) the layer shows the number and a 4-digit code; the gateway is
// long-polled with the code's token until a call keys it, and that call's log is then read from the
// gateway with the token the claim returns. With `phone` alone it shows the number, and with
// `log-url` it follows the agent's live phone call through the site's own relay.

import { ICONS } from "./markup.js";
import { fill, refusalOf } from "./texts.js";

// Must match the entry types a log-url relay requests.
const LOG_TYPES = "call.started,user.transcript,agent.transcript,turn.user,turn.agent,tool.call,tool.result,call.ended";
// How often the site's relay is asked for the agent's phone calls while "Call us" is open, in ms.
const POLL_MS = 1000;

/** A NANP number as +1 XXX XXX XXXX; any other is returned as it came. */
function spaced(number) {
  const nanp = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(number);
  return nanp ? `+1 ${nanp[1]} ${nanp[2]} ${nanp[3]}` : number;
}

/**
 * One phone call's log as a transcript: the caller's turns, the agent's, and its tool calls in log
 * order, the agent's words shown as its voice says them. The tools toggle shows or hides tool lines.
 */
class Transcript {
  constructor(list, scroller, showTools, words) {
    this.list = list;
    this.scroller = scroller;
    this.showTools = showTools;
    this.words = words;
    this.stream = null;
    this.lines = new Map();
    this.hearing = null;
    this.seen = 0;
  }

  follow(url, attempt = 0) {
    this.stop();
    if (attempt === 0) {
      this.list.replaceChildren();
      this.lines.clear();
      this.hearing = null;
      this.seen = 0;
    }
    const stream = new EventSource(url);
    this.stream = stream;
    // A new EventSource has no Last-Event-ID, so a reconnect replays the log from the start: entries
    // already drawn are skipped by their seq. Not `lastEventId`: an event without one inherits the last.
    const on = (type, draw) =>
      stream.addEventListener(type, (event) => {
        const seq = JSON.parse(event.data).seq;
        if (typeof seq === "number") {
          if (seq <= this.seen) return;
          this.seen = seq;
        }
        draw(JSON.parse(event.data).data ?? {});
      });
    stream.onerror = () => {
      if (stream.readyState !== EventSource.CLOSED) return;
      stream.close();
      if (this.stream === stream && attempt < 10) setTimeout(() => this.follow(url, attempt + 1), 1000);
    };
    // The caller's line settles on the final transcript; `turn.user` comes later, after the utterance ends.
    on("user.transcript", (heard) => {
      if (!this.hearing) this.hearing = this.line("user interim", "");
      this.hearing.textContent = heard.text ?? "";
      if (heard.final) this.hearing.className = "user";
      this.scroll();
    });
    on("turn.user", (turn) => {
      const item = this.hearing ?? this.line("user", "");
      item.className = "user";
      item.textContent = turn.text ?? "";
      this.hearing = null;
    });
    on("agent.transcript", (word) => this.spoken(`speech_${word.speech_id}`, word.text ?? "", word.start));
    on("turn.agent", (turn) => this.said(`speech_${turn.speech_id}`, turn.text ?? ""));
    on("tool.call", (tool) => this.mark(`→ ${tool.name}(${JSON.stringify(tool.arguments ?? {})})`));
    on("tool.result", (result) => this.mark(`← ${result.name}: ${result.error ?? JSON.stringify(result.output ?? "").slice(0, 120)}`));
    on("call.ended", (ended) => {
      this.mark(fill(this.words.endedWhy, { why: ended.reason ?? "" }), true);
      this.stop();
    });
  }

  stop() {
    this.stream?.close();
    this.stream = null;
    for (const item of this.lines.values()) item.pace?.timers.forEach(clearTimeout);
  }

  /**
   * One agent word in step with its voice. Words arrive before they play, with a start time relative
   * to the speech, counted from the first word's arrival; a word with no time shows at once.
   */
  spoken(key, text, start) {
    let item = this.lines.get(key);
    if (!item) {
      item = this.line("agent interim", "");
      this.lines.set(key, item);
      item.pace = { anchor: performance.now(), last: 0, timers: [] };
    }
    const pace = item.pace;
    if (!pace) return;
    const show = () => {
      item.textContent += text;
      this.scroll();
    };
    const due = typeof start === "number" ? Math.max(pace.anchor + start * 1000, pace.last) : performance.now();
    pace.last = due;
    const wait = due - performance.now();
    if (wait <= 0) show();
    else pace.timers.push(setTimeout(show, wait));
  }

  /** The agent's turn as it was said, in place of its words still pacing. */
  said(key, text) {
    let item = this.lines.get(key);
    if (!item) {
      item = this.line("agent", "");
      this.lines.set(key, item);
    }
    item.pace?.timers.forEach(clearTimeout);
    item.pace = null;
    item.className = "agent";
    item.textContent = text;
    this.scroll();
  }

  /** A line of the log that is not a turn; a tool's shows only while the toggle is on. */
  mark(text, always = false) {
    const item = this.line("mark", text);
    if (!always) {
      item.dataset.tool = "";
      item.hidden = !this.showTools();
    }
  }

  line(className, text) {
    const item = document.createElement("li");
    item.className = className;
    item.textContent = text;
    this.list.append(item);
    this.scroll();
    return item;
  }

  tools(shown) {
    for (const item of this.list.querySelectorAll("li[data-tool]")) item.hidden = !shown;
  }

  scroll() {
    this.scroller.scrollTop = this.scroller.scrollHeight;
  }
}

export class CallUs {
  constructor(widget) {
    this.widget = widget;
    this.toolsKey = `pinecall-widget:show-tools:${widget.agent}`;
    this.transcript = null;
    this.poll = null;
    this.wait = null;
    this.clock = null;
    // The menu of the two calls while it is open: the function that closes it.
    this.chooser = null;
  }

  /** Both calls offered: a small menu under the call button says which, in the browser or from the phone. */
  choose() {
    if (this.chooser) return this.closeChooser();
    const widget = this.widget;
    const words = widget.words;
    const menu = document.createElement("div");
    menu.className = "choose";
    menu.setAttribute("role", "menu");
    const row = (icon, title, sub, pick) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "menuitem");
      button.innerHTML = `<i>${icon}</i><span><b></b><small></small></span>`;
      button.querySelector("b").textContent = title;
      button.querySelector("small").textContent = sub;
      button.addEventListener("click", () => {
        this.closeChooser();
        pick();
      });
      return button;
    };
    const panel = widget.$(".panel");
    const outside = (event) => {
      if (!event.composedPath().some((node) => node === menu || node === widget.$(".call"))) this.closeChooser();
    };
    const onKey = (event) => {
      if (event.key === "Escape") this.closeChooser();
    };
    this.chooser = () => {
      menu.remove();
      panel.removeEventListener("pointerdown", outside);
      widget.removeEventListener("keydown", onKey);
      this.chooser = null;
    };
    menu.append(
      row(ICONS.mic, words.talkHere, words.talkHereSub, () => widget.startCall()),
      row(ICONS.phone, words.callUs, this.byCode ? words.callUsByCode : words.callUsSub, () => this.open()),
    );
    panel.addEventListener("pointerdown", outside);
    widget.addEventListener("keydown", onKey);
    widget.$("header").append(menu);
  }

  closeChooser() {
    this.chooser?.();
  }

  get logUrl() {
    return this.widget.getAttribute("log-url") ?? "";
  }

  get phone() {
    return this.widget.getAttribute("phone") ?? "";
  }

  /** Whether "Call us" ties the call to the page with a code. */
  get byCode() {
    return Boolean(this.widget.getAttribute("code-url") || this.widget.codeProvider);
  }

  /** Whether the page offers a call from the visitor's phone at all. */
  get offered() {
    return this.byCode || Boolean(this.phone);
  }

  showTools() {
    try {
      return localStorage.getItem(this.toolsKey) === "1";
    } catch {
      return false;
    }
  }

  /** The layer, its number and, with a code, the code; the call's lines follow as soon as it is on. */
  open() {
    const widget = this.widget;
    const layer = widget.layer(widget.words.callUs);
    widget.onLayerClosed = () => this.stop();
    if (this.logUrl) layer.querySelector(".layer-bar").append(this.toolsToggle());
    const body = layer.querySelector(".layer-body");
    if (this.byCode) void this.code(body);
    else this.number(body);
  }

  /** "Show tools": the tool calls of the phone call's log, shown or hidden, the choice kept. */
  toolsToggle() {
    const label = document.createElement("label");
    label.className = "tools";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = this.showTools();
    box.addEventListener("change", () => {
      try {
        localStorage.setItem(this.toolsKey, box.checked ? "1" : "0");
      } catch {
        // storage unavailable: the toggle holds for this page
      }
      this.transcript?.tools(box.checked);
    });
    label.append(box, document.createTextNode(this.widget.words.showTools));
    return label;
  }

  stop() {
    clearInterval(this.poll);
    this.poll = null;
    this.wait?.abort();
    this.wait = null;
    clearInterval(this.clock);
    this.clock = null;
    this.transcript?.stop();
    this.transcript = null;
  }

  /** The number to call, as a line with its button: set as text, never HTML, for it is the site's. */
  dialLine(number) {
    const line = document.createElement("div");
    line.className = "number";
    line.innerHTML = `<b></b><a>${ICONS.phone}<span></span></a>`;
    line.querySelector("b").textContent = spaced(number);
    line.querySelector("a").href = `tel:${number.replace(/[^\d+]/g, "")}`;
    line.querySelector("a span").textContent = this.widget.words.dial;
    return line;
  }

  /** The phone call's lines, read from its log. */
  follow(body, lines, url, mark) {
    this.transcript = new Transcript(lines, body, () => this.showTools(), this.widget.words);
    this.transcript.follow(url);
    this.transcript.mark(mark, true);
  }

  /** `phone` alone: the number, and with `log-url` the agent's phone call that is live, or one started since this opened. */
  number(body) {
    const words = this.widget.words;
    const status = document.createElement("span");
    status.className = "status";
    status.textContent = this.logUrl ? words.waiting : words.callTheNumber;
    const lines = document.createElement("ul");
    lines.className = "lines";
    body.append(this.dialLine(this.phone), status, lines);
    if (!this.logUrl) return;
    const agent = encodeURIComponent(this.widget.agent);
    const log = (query) => `${this.logUrl}${this.logUrl.includes("?") ? "&" : "?"}agent=${agent}&${query}`;
    const openedAt = Date.now() / 1000 - 5;
    let showing = null;
    const poll = async () => {
      try {
        const answer = await fetch(log("list=1"));
        if (!answer.ok) throw new Error(`log: HTTP ${answer.status}`);
        const { calls } = await answer.json();
        const live = calls.find((call) => call.live);
        status.textContent = live ? words.onTheLine : words.waiting;
        status.className = `status${live ? " live" : ""}`;
        const current = live ?? calls.find((call) => (call.started_at ?? 0) >= openedAt);
        if (current && showing !== current.call) {
          showing = current.call;
          this.transcript?.stop();
          this.follow(body, lines, log(`call=${encodeURIComponent(current.call)}`), fill(words.callFrom, { who: current.from }));
        }
      } catch (failed) {
        status.textContent = failed.message;
        status.className = "status failed";
      }
    };
    void poll();
    this.poll = setInterval(poll, POLL_MS);
  }

  /** {code, number, expires_at, code_token}, from `codeProvider` or `code-url`. */
  async askCode() {
    const widget = this.widget;
    if (widget.codeProvider) return widget.codeProvider(widget.agent);
    const answer = await fetch(widget.getAttribute("code-url"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: widget.agent }),
    });
    const said = await answer.json().catch(() => ({}));
    if (!answer.ok) throw new Error(refusalOf(said, `code: HTTP ${answer.status}`));
    return said;
  }

  /**
   * With a code: ask for one, show the number and its digits, and long-poll the gateway with the
   * code's token (up to 25 s a request) until a call claims it; then follow that call's log.
   */
  async code(body) {
    const widget = this.widget;
    const words = widget.words;
    body.replaceChildren();
    const status = document.createElement("span");
    status.className = "status";
    status.textContent = words.gettingCode;
    body.append(status);
    let code;
    try {
      code = await this.askCode();
      if (!(typeof code?.code === "string" && typeof code.number === "string" && typeof code.code_token === "string"))
        throw new Error("the code endpoint answered with something this widget does not know");
    } catch (refused) {
      status.textContent = refused.message;
      status.className = "status failed";
      return;
    }
    const dial = document.createElement("div");
    dial.className = "dial";
    dial.innerHTML = `
      <div class="step"><span class="n">1</span><span class="say"></span></div>
      <div class="step"><span class="n">2</span><span class="say"><span></span> <small></small></span><div class="digits" role="img"></div></div>
      <div class="waiting"></div>`;
    const [first, second] = dial.querySelectorAll(".step");
    first.querySelector(".say").textContent = words.callName;
    first.append(this.dialLine(code.number));
    second.querySelector(".say > span").textContent = words.keyCode;
    second.querySelector(".say small").textContent = `· ${words.anyTime}`;
    const digits = second.querySelector(".digits");
    for (const digit of code.code) digits.append(Object.assign(document.createElement("span"), { textContent: digit }));
    digits.setAttribute("aria-label", fill(words.theCode, { digits: code.code.split("").join(" ") }));
    const expires = document.createElement("span");
    expires.className = "expires";
    status.textContent = words.waiting;
    dial.querySelector(".waiting").append(status, expires);
    const soon = document.createElement("div");
    soon.className = "soon";
    soon.textContent = words.showsHere;
    const lines = document.createElement("ul");
    lines.className = "lines";
    lines.hidden = true;
    body.replaceChildren(dial, soon, lines);
    const left = () => {
      const seconds = Math.max(0, Math.floor(code.expires_at - Date.now() / 1000));
      expires.textContent = fill(words.expiresIn, { left: `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` });
    };
    left();
    this.clock = setInterval(left, 1000);
    const stop = new AbortController();
    this.wait = stop;
    const failed = (said, again = false) => {
      clearInterval(this.clock);
      this.clock = null;
      status.textContent = said;
      status.className = "status failed";
      if (!again) return;
      const fresh = document.createElement("button");
      fresh.type = "button";
      fresh.className = "pill";
      fresh.textContent = words.newCode;
      fresh.addEventListener("click", () => void this.code(body));
      body.append(fresh);
    };
    const asked = `${widget.gateway}/v1/codes/${encodeURIComponent(code.code)}?wait=1&token=${encodeURIComponent(code.code_token)}`;
    while (!stop.signal.aborted) {
      let standing;
      try {
        const answer = await fetch(asked, { signal: stop.signal });
        // A 5xx or the network is tried again; any other refusal is final.
        if (answer.status >= 500) throw new Error(`code: HTTP ${answer.status}`);
        standing = await answer.json();
        if (!answer.ok) throw Object.assign(new Error(refusalOf(standing, `code: HTTP ${answer.status}`)), { final: true });
      } catch (refused) {
        if (stop.signal.aborted) return;
        if (refused.final) return failed(refused.message);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        continue;
      }
      if (standing.status === "expired") return failed(words.codeExpired, true);
      if (standing.status !== "claimed") continue;
      clearInterval(this.clock);
      this.clock = null;
      dial.remove();
      soon.remove();
      lines.hidden = false;
      status.textContent = words.onTheLine;
      status.className = "status live";
      lines.before(status);
      const call = encodeURIComponent(standing.call);
      const url = `${widget.gateway}/v1/calls/${call}/events?types=${LOG_TYPES}&after=0&token=${encodeURIComponent(standing.log_token)}`;
      this.follow(body, lines, url, words.yourCall);
      return;
    }
  }
}
