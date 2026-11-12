// <pinecall-widget>: one Pinecall agent as one button on any page. The button opens a chat straight
// away; a voice call from the browser is one tap in the panel's header, and so is "Call us", a call
// from the visitor's own phone that shows up live in the panel, when the page offers one. The page's
// own server mints the tokens with the org's key, so the key never reaches the browser.
//
//   <script type="module" src="https://cloud.pinecall.io/widget/pinecall-widget.js"></script>
//   <pinecall-widget agent="pip" name="Pip" company="Brightside Dental" token-url="/pinecall/token"></pinecall-widget>
//
// Attributes, read once when the tag connects (token-url for every token):
//   agent          required · the agent's slug
//   token-url      required unless `tokenProvider` is set · POST {agent, scope, resume?} → the gateway's token
//   name · company · tagline   who answers, shown in the header; name is "Assistant" when left out
//   lang           the widget's own words: en (default) or es
//   text-<key>     any one of those words, e.g. text-add-to-cart="Add to bag" (texts.js lists the keys)
//   greeting       the agent's first line, shown until its own first words replace it
//   label          the button's text, shown beside its icon; without it the button is the icon alone
//   icon           "none" leaves the button its label alone
//   button         "none" draws no button: open the panel with toggle(); a child with slot="button" replaces it
//   position       bottom-right (default), bottom-left, top-right, top-left, or inline
//   theme          auto (default: the machine's, switched by the visitor from the header), light or dark
//   autostart      the opening click starts a voice call, the microphone asked inside it
//   call           "off" takes the browser voice call away
//   phone          the number "Call us" shows
//   code-url       POST {agent} → a 4-digit code that ties the visitor's phone call to the page
//   log-url        the site's relay of the agent's phone calls and their logs, for "Call us" with a number alone
//   gateway        where codes, their calls' logs and hang-ups go; this file's origin by default
//   dictation-url  POST ?language= → a socket that writes the visitor's dictated words into the field
//   dictation      "off" takes dictation away
//   history        "off" keeps nothing in this browser; by default the conversation under way survives a
//                  reload, and the last 20 are listed under "Your conversations"
//   look="dot"     the button is a face that speaks with the agent's voice (pinecall-dot.js), with
//                  tutor, walks, ask, shape, color and captions as that file says
//
// Properties: tokenProvider (scope, agent, resume) => token, codeProvider (agent) => code, texts
// {key: words}, views (the dot tutor's tool cards). Methods: toggle(), event(name, data).
// Events: pinecall:open; pinecall:started {call, scope}; pinecall:ended {call}; pinecall:ui, with
// {action: "open", url} when the visitor taps a link of the page's own site (cancel it to route it
// yourself), and with look="dot" whatever the agent sent on pinecall.ui.
// Styling: --pc-accent, --pc-on-accent, --pc-accent-soft, --pc-ink, --pc-muted, --pc-line, --pc-surface,
// --pc-header-bg, --pc-radius, --pc-font, --pc-font-size, --pc-z, --pc-offset, --pc-panel-width,
// --pc-panel-height, --pc-button-bg, --pc-button-ink, --pc-button-border, --pc-button-radius,
// --pc-button-padding, --pc-button-shadow, --pc-button-weight, --pc-button-font-size, --pc-dot-size.
// Parts: button, button-icon, button-label, panel (and the dot's button-face, bubble).
//
// The agent draws with call.send("pinecall.ui", data): html, choices, products (event cart.add), form
// (its own event) and form-fill, and cart, kept with the conversation and given back to the call
// that follows one that ended (event cart.restored). README.md is the whole reference.

// Pinned: a floating @2 took 2.23.0, which signals on /rtc/v1, a path Pinecall's gateway does not route.
import { Room, RoomEvent, Track } from "https://cdn.jsdelivr.net/npm/livekit-client@2.22.3/+esm";
import { CallUs } from "./call-us.js";
import { card } from "./cards.js";
import { Dictation } from "./dictation.js";
import { Kept, listKept } from "./history.js";
import { Lines } from "./lines.js";
import { ICONS } from "./markup.js";
import { Panel } from "./panel.js";
import { PHONE, STYLE } from "./styles.js";
import { languageOf, wordsOf } from "./texts.js";

const TRANSCRIPTION = "lk.transcription";
const CHAT = "lk.chat";
// Said before leaving on a hang-up: the call ends at once instead of waiting for the visitor.
const HANGUP = "pinecall.hangup";
const UI = "pinecall.ui";
// A fact about the page, for the agent's onEvent: {name, data}.
const EVENT = "pinecall.event";
// Default gateway: the origin that served this file, or Pinecall's when served from the CDN.
const SERVED_FROM = new URL(import.meta.url).origin;
const A_GATEWAY = SERVED_FROM.includes("jsdelivr.net") ? "https://cloud.pinecall.io" : SERVED_FROM;

const TEMPLATE = `
  <style>${STYLE}</style>
  <slot name="button"></slot>
  <button class="fab" part="button" type="button"><span class="icon" part="button-icon">${ICONS.chat}</span><span class="label" part="button-label"></span></button>
  <button class="peek" type="button" hidden><span class="peek-who"></span><span class="peek-text"></span></button>
  <div class="scrim" hidden></div>
  <section class="panel" part="panel" hidden role="dialog">
    <header>
      <span class="avatar" aria-hidden="true"></span>
      <div class="who"><h2></h2><p></p></div>
      <button class="tool kept-tool" type="button" hidden>${ICONS.clock}</button>
      <button class="tool theme" type="button"></button>
      <button class="tool call" type="button"></button>
      <button class="tool fresh" type="button">${ICONS.fresh}</button>
      <button class="tool maximize" type="button"></button>
      <button class="tool close" type="button">×</button>
    </header>
    <div class="body"><span class="status"></span><ul class="lines"></ul></div>
    <footer>
      <div class="field">
        <input type="text" autocomplete="off" enterkeyhint="send">
        <button class="mic" type="button">${ICONS.mic}</button>
        <button class="send" type="button" disabled>${ICONS.send}</button>
      </div>
    </footer>
    <div class="edge edge-x" data-axis="x"></div>
    <div class="edge edge-y" data-axis="y"></div>
    <div class="edge grip" data-axis="xy" role="separator"></div>
  </section>`;

/** What goes on pinecall.event: the name and the data, as JSON. */
function packet(name, data) {
  return new TextEncoder().encode(JSON.stringify({ name, data }));
}

class PinecallWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.room = null;
    this.scope = null;
    // The conversation under way, as it is kept.
    this.current = null;
    this.opening = null;
    this.minimized = false;
    this.built = false;
    // The forms the agent put on screen, by id, each the function that fills it as she speaks.
    this.forms = new Map();
    // The call under way and a token of its own, to say its hang-up at the gateway's door.
    this.hangup = null;
    this.overrides = null;
    this.onLayerClosed = null;
    // `texts` set on the tag before this file defined it is an own property: taken through the setter.
    if (Object.hasOwn(this, "texts")) {
      const texts = this.texts;
      delete this.texts;
      this.texts = texts;
    }
  }

  /** The page's own words for any key of the texts table, over the language's and the `text-*` attributes. */
  get texts() {
    return this.overrides;
  }

  set texts(value) {
    this.overrides = value && typeof value === "object" ? value : null;
    if (this.built) this.relabel();
  }

  /** Whether the browser voice call is offered. */
  get talks() {
    return this.getAttribute("call") !== "off";
  }

  // ── the element ───────────────────────────────────────────────────────────────

  // Persisted across a site's page changes, the element is connected again: built once.
  connectedCallback() {
    if (this.built) {
      this.panel.hold();
      return;
    }
    this.built = true;
    this.agent = this.getAttribute("agent") ?? "";
    this.lang = languageOf(this);
    this.company = this.getAttribute("company") ?? "";
    this.tagline = this.getAttribute("tagline") ?? "";
    this.greeting = this.getAttribute("greeting") ?? "";
    this.gateway = (this.getAttribute("gateway") ?? A_GATEWAY).replace(/\/+$/, "");
    // Present means on, unless the value is "false".
    this.autostart = this.hasAttribute("autostart") && this.getAttribute("autostart") !== "false";
    this.kept = new Kept(this.agent, this.getAttribute("history") !== "off");
    this.openKey = `pinecall-widget:open:${this.agent}`;
    this.shadowRoot.innerHTML = TEMPLATE;
    this.$ = (selector) => this.shadowRoot.querySelector(selector);
    this.panel = new Panel(this);
    this.lines = new Lines(this);
    this.dictation = new Dictation(this);
    this.callUs = new CallUs(this);
    this.relabel();
    this.wire();
    this.panel.sizing();
    this.panel.theming();
    this.keptChanged();
    matchMedia(PHONE).addEventListener("change", () => this.panel.hold());
    // look="dot": the face and its call, from the module beside this file; until it has loaded, a
    // click waits for it, and a dot that cannot load leaves the plain button.
    if (this.getAttribute("look") === "dot") {
      this.$(".fab").style.visibility = "hidden";
      this.dotting = import("./pinecall-dot.js").then(
        ({ Dot }) => (this.dot = new Dot(this)),
        (failed) => {
          console.warn("pinecall-widget: the dot could not load, so the button is the plain one", failed);
          this.$(".fab").style.visibility = "";
          return null;
        },
      );
      return;
    }
    // Back on the page with the panel open (a reload): open again where it was. Deferred, and only
    // for an element still on the page: a router builds a page's own element before it puts the
    // persisted one in its place, and that one must not open a room of its own.
    setTimeout(() => {
      try {
        if (this.isConnected && sessionStorage.getItem(this.openKey) === "1" && this.$(".panel").hidden) this.toggle();
      } catch {
        // storage unavailable
      }
    }, 0);
  }

  // A widget taken off the page lets the page go; the conversation waits, as on a reload.
  disconnectedCallback() {
    this.dot?.close();
    this.panel.release();
  }

  /** The words the tag says, and every label drawn with them. */
  relabel() {
    this.name = this.getAttribute("name") ?? wordsOf(this, this.lang, this.overrides, {}).assistant;
    this.words = wordsOf(this, this.lang, this.overrides, { name: this.name, company: this.company });
    const words = this.words;
    // The dot owns the button once it has loaded.
    const label = this.$(".fab .label");
    if (label) {
      const fab = this.$(".fab");
      const own = this.getAttribute("label");
      const bare = this.getAttribute("icon") === "none";
      label.textContent = own ?? words.open;
      label.hidden = own === null && !bare;
      fab.querySelector(".icon").hidden = bare;
      fab.classList.toggle("labelled", !label.hidden);
      if (label.hidden) fab.ariaLabel = words.open;
      else fab.removeAttribute("aria-label");
    }
    // Set as text, never HTML: a page that interpolates these from elsewhere must not get markup through here.
    this.$(".peek-who").textContent = this.name;
    this.$(".panel").ariaLabel = words.open;
    this.$("header .avatar").textContent = (this.name.trim()[0] ?? "A").toUpperCase();
    this.$("header h2").textContent = this.name;
    this.$("header p").textContent = [this.company, this.tagline].filter(Boolean).join(" · ");
    const kept = this.$(".kept-tool");
    kept.title = kept.ariaLabel = words.history;
    const fresh = this.$(".fresh");
    fresh.title = fresh.ariaLabel = words.fresh;
    this.$(".close").ariaLabel = words.close;
    const input = this.$("footer input");
    input.placeholder = this.dictation.active ? words.hearing : words.write;
    input.ariaLabel = words.write;
    this.$(".mic").ariaLabel = this.dictation.active ? words.stopDictating : words.dictate;
    this.$(".send").ariaLabel = words.send;
    this.panel.label();
    this.panel.themeLabel();
    this.callButton();
  }

  /** What every button and field of the panel does. */
  wire() {
    const open = () => {
      if (this.dot) return this.dot.click();
      if (this.dotting) return this.dotting.then((dot) => (dot ? dot.click() : this.toggle()));
      return this.autostart ? this.start() : this.toggle();
    };
    // The page's own launcher, when it gives one: a child with slot="button" replaces the button, and
    // whatever it is opens the panel. button="none" draws none.
    const slot = this.$('slot[name="button"]');
    const launch = () => {
      const own = slot.assignedElements();
      this.$(".fab").hidden = own.length > 0 || this.getAttribute("button") === "none";
      for (const element of own) {
        // The mark is an empty string, which reads false: ask whether it is there, not what it says.
        if ("pinecallOpens" in element.dataset) continue;
        element.dataset.pinecallOpens = "";
        element.addEventListener("click", (event) => {
          event.preventDefault();
          open();
        });
      }
    };
    slot.addEventListener("slotchange", launch);
    launch();
    this.$(".fab").addEventListener("click", open);
    this.$(".peek").addEventListener("click", () => this.toggle());
    // A link of the page's own site in a card is handed to the page first (pinecall:ui, `open`): a
    // page that routes it cancels the event, and on a phone the chat steps aside so the page is seen.
    this.$(".lines").addEventListener("click", (event) => {
      const link = event.composedPath().find((node) => node instanceof HTMLAnchorElement);
      if (!link || new URL(link.href).origin !== location.origin) return;
      const to = new URL(link.href);
      const detail = { action: "open", url: to.pathname + to.search };
      if (this.dispatchEvent(new CustomEvent("pinecall:ui", { detail, cancelable: true }))) return;
      event.preventDefault();
      this.minimize();
    });
    this.$(".close").addEventListener("click", () => this.hide());
    this.$(".call").addEventListener("click", () => this.callTapped());
    this.$(".fresh").addEventListener("click", () => this.fresh());
    this.$(".kept-tool").addEventListener("click", () => listKept(this));
    const input = this.$("footer input");
    const send = async () => {
      if (this.dictation.active) await this.dictation.stop();
      return this.typed(input);
    };
    this.$(".send").addEventListener("click", send);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") send();
    });
    // The send lights up with words to send.
    input.addEventListener("input", () => (this.$(".send").disabled = !input.value.trim()));
    this.$(".mic").addEventListener("click", () => (this.dictation.active ? this.dictation.stop() : this.dictation.start()));
    this.$(".field").dataset.state = "";
  }

  // ── the conversations kept in this browser ─────────────────────────────────────

  keep() {
    if (this.current) this.kept.put(this.current);
    this.keptChanged();
  }

  /** The conversations before the one under way. */
  past() {
    const under = this.current ?? this.kept.current();
    return this.kept.all().filter((one) => one.call !== under?.call);
  }

  /** "Your conversations" is in the header while there is one to read again. */
  keptChanged() {
    this.$(".kept-tool").hidden = this.past().length === 0;
  }

  /**
   * A conversation just opened, kept from now on as its lines settle. One carried on (`earlier`)
   * stays one conversation: its lines, its cart, the new call and the token to resume it next.
   */
  began(call, scope, resume = null, earlier = null) {
    // Only one conversation is under way: one that is not carried on here has ended.
    if (this.current && this.current.call !== earlier?.call) this.ended();
    this.current = {
      call, scope, agent: this.agent, started_at: earlier?.started_at ?? Date.now(), ended_at: null,
      lines: earlier?.lines ?? [], resume, cart: earlier?.cart ?? [],
    };
    this.kept.put(this.current, earlier ? [earlier.call] : []);
    this.keptChanged();
  }

  /** One settled line of the conversation under way; the same key again replaces it. */
  keptLine(key, who, text) {
    const current = this.current;
    if (!current || !text) return;
    // Keyed by call: a carried-on conversation's calls number their lines alike.
    key = `${current.call}:${key}`;
    const at = current.lines.findIndex((one) => one.key === key);
    if (at >= 0) current.lines[at] = { key, who, text };
    else current.lines.push({ key, who, text });
    this.keep();
  }

  /** The conversation under way is over: it goes to the ones kept before. */
  ended() {
    if (!this.current) return;
    this.current.ended_at = Date.now();
    this.keep();
    this.current = null;
    this.keptChanged();
  }

  forgetAll() {
    this.kept.clear(this.current ?? this.kept.current());
    this.keptChanged();
  }

  /** A kept conversation carried on: the one under way ends, and this one takes its place as a chat. */
  async carryOn(one) {
    await this.fresh({ ...one, ended_at: null });
  }

  // ── open, close ────────────────────────────────────────────────────────────────

  toggle() {
    if (!this.$(".panel").hidden) return this.hide();
    this.show();
    if (!this.room && !this.opening) void this.conversation("chat");
    else this.$("footer input").focus();
  }

  /** The panel on screen, whatever it opens into. */
  show() {
    this.$(".peek").hidden = true;
    this.$(".panel").hidden = false;
    this.panel.hold();
    try {
      sessionStorage.setItem(this.openKey, "1");
    } catch {
      // storage unavailable
    }
    this.minimized = false;
    this.dispatchEvent(new CustomEvent("pinecall:open"));
  }

  /** `autostart`: the opening click is a voice call, the microphone asked inside it; refused, a chat. */
  async start() {
    if (!this.$(".panel").hidden) return this.hide();
    this.show();
    if (this.room || this.opening) return;
    if (!(this.talks && (await this.startCall()))) await this.conversation("chat");
  }

  /** On a phone, step aside so the page shows: the panel hides, the conversation stays connected. */
  minimize() {
    if (!matchMedia(PHONE).matches) return;
    const panel = this.$(".panel");
    if (panel.hidden) return;
    panel.hidden = true;
    this.minimized = true;
    this.panel.hold();
  }

  /** Minimized, the agent's newest line waits over the button. */
  peek(text) {
    if (!this.minimized) return;
    this.$(".peek-text").textContent = text;
    this.$(".peek").hidden = false;
  }

  // Closing leaves the room without hanging up: the conversation waits, and opens again where it was.
  async hide() {
    this.minimized = false;
    this.closeLayer();
    this.callUs.closeChooser();
    this.$(".peek").hidden = true;
    this.$(".panel").hidden = true;
    this.panel.hold();
    try {
      sessionStorage.removeItem(this.openKey);
    } catch {
      // storage unavailable
    }
    // An open still in flight lands first, or its room would outlive the panel.
    await this.opening?.catch(() => undefined);
    await this.leave();
  }

  /** The visitor starts over: the conversation under way ends, and a new one opens (or `carried`, one kept). */
  async fresh(carried = null) {
    this.closeLayer();
    await this.hungUp();
    await this.leave();
    this.ended();
    this.lines.clear();
    if (carried) {
      this.current = carried;
      this.keep();
    }
    await this.conversation("chat");
  }

  /** A layer over the conversation, under its title; its back arrow returns to the conversation unless told otherwise. */
  layer(title, back = () => this.closeLayer()) {
    this.closeLayer();
    // The field goes under the layer, and a dictation with it.
    void this.dictation.stop();
    const layer = document.createElement("div");
    layer.className = "layer";
    layer.innerHTML = `<div class="layer-bar"><button class="tool back" type="button">${ICONS.back}</button><h3></h3></div><div class="layer-body"></div>`;
    const button = layer.querySelector(".back");
    button.title = button.ariaLabel = this.words.backToChat;
    button.addEventListener("click", back);
    layer.querySelector("h3").textContent = title;
    this.$(".body").append(layer);
    this.$(".panel").classList.add("layered");
    return layer;
  }

  closeLayer() {
    this.onLayerClosed?.();
    this.onLayerClosed = null;
    this.$(".layer")?.remove();
    this.$(".panel").classList.remove("layered");
  }

  // ── calls ──────────────────────────────────────────────────────────────────────

  /** The header's call button: hang up to the chat, or call, in the browser or from the visitor's phone. */
  callTapped() {
    if (this.scope === "talk") return this.conversation("chat");
    if (this.talks && this.callUs.offered) return this.callUs.choose();
    if (this.callUs.offered) return this.callUs.open();
    return this.startCall();
  }

  /** A voice call in the browser; the microphone is asked for inside the tap, as browsers require. Refused, the chat goes on. */
  async startCall() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
    } catch {
      this.notice(this.words.micRefused);
      return false;
    }
    await this.conversation("talk");
    return true;
  }

  /** The call button as the call is: a phone, or a hang-up during a voice call; the microphone is the call's then. */
  callButton() {
    const words = this.words;
    const button = this.$(".call");
    const on = this.scope === "talk";
    button.hidden = !(this.talks || this.callUs.offered);
    button.classList.toggle("on", on);
    button.innerHTML = on ? ICONS.hang : ICONS.phone;
    button.title = button.ariaLabel = on ? words.hangUpToChat : this.talks ? words.call : words.callUs;
    this.$(".mic").hidden = on || !this.dictation.offered;
    if (on) void this.dictation.stop();
  }

  // ── the conversation ───────────────────────────────────────────────────────────

  /**
   * Open the conversation in this scope. One kept in this browser is carried on with its resume
   * token, chat or call alike, so the agent reads what was said; its lines are drawn first.
   */
  async conversation(scope) {
    const earlier = this.current ?? this.kept.current();
    if (earlier && this.lines.empty) this.lines.drawKept(earlier.lines);
    if (!earlier && this.greeting && this.lines.empty) this.lines.hello(this.greeting);
    this.status(this.words.connecting);
    this.opening = this.open(scope, earlier);
    try {
      await this.opening;
    } catch (failed) {
      this.status(failed?.message ?? this.words.failed, "failed");
    } finally {
      this.opening = null;
    }
  }

  /** A token for this scope, from `tokenProvider` or `token-url`. */
  async token(scope, resume = null) {
    if (typeof this.tokenProvider === "function") return this.tokenProvider(scope, this.agent, resume ?? undefined);
    const url = this.getAttribute("token-url");
    if (!url) throw new Error("pinecall-widget: token-url is missing");
    if (!this.agent) throw new Error("pinecall-widget: agent is missing");
    const answer = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: this.agent, scope, ...(resume ? { resume } : {}) }),
    });
    const minted = await answer.json().catch(() => ({}));
    if (!answer.ok) throw new Error(minted.detail ?? this.words.failed);
    if (typeof minted?.server_url !== "string" || typeof minted?.participant_token !== "string") throw new Error(this.words.failed);
    return minted;
  }

  async open(scope, earlier) {
    await this.leave();
    this.lines.forgetStreams();
    // A call opened as a chat listens to no microphone, ever: a voice call is a call of its own, opened
    // fresh, with the chat's lines still on screen and its cart carried over. Back to chat, the voice
    // call is carried on: it reads what is typed.
    if (scope === "talk" && earlier) earlier = { ...earlier, resume: null };
    let resumed = Boolean(earlier?.resume);
    let minted;
    try {
      minted = await this.token(scope, earlier?.resume ?? null);
    } catch (refused) {
      // A resume the gateway no longer takes: a fresh conversation, its lines kept on screen.
      if (!earlier?.resume) throw refused;
      minted = await this.token(scope, null);
      earlier = { ...earlier, resume: null };
      resumed = false;
    }
    const room = new Room();
    this.room = room;
    this.scope = scope;
    this.greeted = new Promise((resolve) => {
      this.onGreeted = resolve;
    });
    room.registerTextStreamHandler(TRANSCRIPTION, (reader, from) => this.lines.read(reader, from.identity));
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (scope !== "talk" || track.kind !== Track.Kind.Audio) return;
      const element = track.attach();
      element.style.display = "none";
      this.shadowRoot.append(element);
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((element) => element.remove()));
    room.on(RoomEvent.DataReceived, (payload, _from, _kind, topic) => {
      if (topic === UI) this.ui(payload);
    });
    // LiveKit reconnects on its own when the network blinks: the conversation goes on. Only a room
    // that is gone for good ends it.
    room.on(RoomEvent.Reconnecting, () => {
      if (this.room === room) this.status(this.words.reconnecting);
    });
    room.on(RoomEvent.Reconnected, () => {
      if (this.room === room) this.status(scope === "talk" ? this.words.listening : this.words.live, "live");
    });
    room.on(RoomEvent.Disconnected, () => {
      if (this.room === room) {
        this.room = null;
        this.scope = null;
        this.status(this.words.ended);
        this.callButton();
      }
      this.dispatchEvent(new CustomEvent("pinecall:ended", { detail: { call: minted.call } }));
    });
    await room.connect(minted.server_url, minted.participant_token);
    // What a hang-up is said with at the gateway's door: the call and a token of its own.
    this.hangup = { call: minted.call, token: minted.log_token ?? minted.participant_token };
    this.began(minted.call, scope, minted.resume_token ?? null, earlier);
    // A new call after one that ended starts with an empty cart: it gets back the one this chat had,
    // once the agent is in the room to hear it.
    const cart = earlier?.cart;
    if (!resumed && cart?.length) void this.greeted.then(() => this.publish("cart.restored", { lines: cart }));
    // A chat goes through a room too: the agent is told when it is a voice call, to speak for the ear.
    if (scope === "talk") void this.greeted.then(() => this.publish("call.spoken", { spoken: true }));
    if (scope === "talk") {
      await room.localParticipant.setMicrophoneEnabled(true);
      if (!room.canPlaybackAudio) this.notice(this.words.tapToHear, () => room.startAudio());
    }
    this.status(scope === "talk" ? this.words.listening : this.words.live, "live");
    this.callButton();
    this.dispatchEvent(new CustomEvent("pinecall:started", { detail: { call: minted.call, scope } }));
    if (scope === "chat" && !matchMedia(PHONE).matches) this.$("footer input").focus();
  }

  async typed(input) {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    this.$(".send").disabled = true;
    if (!(await this.say(text))) input.value = text;
    input.focus();
  }

  /** A line of hers, typed or spoken: drawn as she sends it, sent once the agent is there to read it. */
  async say(text) {
    if (this.opening) await this.opening.catch(() => undefined);
    else if (!this.room) await this.conversation("chat");
    const pending = `typed_${Date.now()}`;
    this.lines.draw(pending, "user interim", text, false);
    try {
      await this.send(text);
      this.lines.draw(pending, "user", text, true);
      return true;
    } catch (failed) {
      this.lines.drop(pending);
      this.status(failed?.message ?? this.words.failed, "failed");
      return false;
    }
  }

  /** A choice tapped is her next line, said as she would type it. */
  async choose(text) {
    const pending = `choice_${Date.now()}`;
    this.lines.draw(pending, "user interim", text, false);
    try {
      await this.send(text);
      this.lines.draw(pending, "user", text, true);
    } catch (failed) {
      this.lines.drop(pending);
      this.status(failed?.message ?? this.words.failed, "failed");
    }
  }

  async send(text) {
    if (!this.room) throw new Error(this.words.failed);
    // Text sent before the agent joins is lost: wait for its first words (8 s at most).
    await Promise.race([this.greeted, new Promise((resolve) => setTimeout(resolve, 8000))]);
    await this.room.localParticipant.sendText(text, { topic: CHAT });
  }

  /** Something the widget tells the agent (a form sent, a product added): false while not connected. */
  publish(name, data) {
    const room = this.room;
    if (!room) return false;
    void room.localParticipant.publishData(packet(name, data), { topic: EVENT, reliable: true });
    return true;
  }

  /**
   * Tell the agent what the visitor did on the page: `{name, data}` on pinecall.event. The agent's
   * onEvent runs when its class accepts the name from a participant. Rejects while no call or chat is open.
   */
  async event(name, data = {}) {
    if (this.dot) return this.dot.event(name, data);
    if (!this.room) throw new Error("not in a call");
    await this.room.localParticipant.publishData(packet(name, data), { topic: EVENT, reliable: true });
  }

  /**
   * Tell the agent the visitor hung up, so the call ends at once instead of waiting for them. Said at
   * the gateway's door first, over HTTP with the call's own token and `keepalive`, which a closing
   * tab still completes; and on the room's data channel, never waited on for long.
   */
  async hungUp() {
    const door = this.hangup;
    this.hangup = null;
    if (door) {
      const said = `${this.gateway}/v1/calls/${encodeURIComponent(door.call)}/hangup?token=${encodeURIComponent(door.token)}`;
      fetch(said, { method: "POST", keepalive: true }).catch(() => undefined);
    }
    const room = this.room;
    if (!room) return;
    const said = room.localParticipant.publishData(new TextEncoder().encode("{}"), { topic: HANGUP, reliable: true });
    try {
      await Promise.race([said, new Promise((resolve) => setTimeout(resolve, 1200))]);
    } catch {
      // unsaid, the call waits for the visitor and ends on its own
    }
  }

  async leave() {
    const room = this.room;
    this.room = null;
    this.scope = null;
    this.hangup = null;
    await Promise.race([room?.disconnect(), new Promise((resolve) => setTimeout(resolve, 3000))]);
  }

  // ── what the agent shows ───────────────────────────────────────────────────────

  /** Something the agent sent on pinecall.ui: a card for the conversation, a form filled, or the cart kept. */
  ui(payload) {
    let data;
    try {
      data = JSON.parse(new TextDecoder().decode(payload));
    } catch {
      return;
    }
    if (!data || typeof data !== "object") return;
    if (data.type === "form-fill" && typeof data.id === "string") {
      this.forms.get(data.id)?.(data.values);
      return;
    }
    if (data.type === "cart" && Array.isArray(data.lines)) {
      if (this.current) {
        this.current.cart = data.lines;
        this.keep();
      }
      return;
    }
    const item = card(this, data);
    if (item) this.lines.shelve(item);
  }

  /** Photos need the whole screen: on a phone, the keyboard goes down when they are shown, and only then. */
  lowerKeyboard() {
    if (!matchMedia(PHONE).matches) return;
    const input = this.$("footer input");
    if (this.shadowRoot.activeElement === input) input.blur();
  }

  /** A line under the status: a refusal that goes by itself, or a button when `tap` is given. */
  notice(text, tap) {
    const line = document.createElement(tap ? "button" : "p");
    line.className = tap ? "notice tap" : "notice";
    line.textContent = text;
    if (tap) {
      line.addEventListener("click", async () => {
        await tap();
        line.remove();
      });
    }
    this.$(".body > .status").after(line);
    if (!tap) setTimeout(() => line.remove(), 6000);
  }

  status(text, tone = "") {
    const status = this.$(".body > .status");
    status.textContent = text;
    status.className = `status ${tone}`;
  }
}

if (!customElements.get("pinecall-widget")) customElements.define("pinecall-widget", PinecallWidget);
