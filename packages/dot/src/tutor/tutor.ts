/** The tutor on a page: the person with its pointer and face, what it sends of the page, and every move the agent asks for. */
//
// Up, as events on the call: the page as it is now (`page.seen`, when it changed, and when a move
// onto an element ended, with the ref it moved to), what the visitor clicked, a ref that is gone.
// Down, from `pinecall.ui`: a cursor move, run at once, or a macro's step, whose moves run on their
// words. Moves run one after another, so a scroll ends before the point that follows it. In words,
// one side at a time: the visitor's as they say them, else the agent's as its voice says them.
// With no call, the walks the agent published play from a button beside the face (`walks`).

import { litAt, sayingOf, type RoomStore } from "@pinecall/room";

import { face } from "../face/index.js";
import type { Shape } from "../face/shape.js";
import { Page } from "../page/page.js";
import { aimOf, along, animate, flightMs, scrollOnto, type Point } from "../pointer/flight.js";
import { Hover } from "../pointer/hover.js";
import { Person, sideOf, type Side } from "../pointer/person.js";
import { fill } from "../pointer/typing.js";
import { A_REF, CLICKED, EXPLAIN, MISSING, MOVED, SEEN, WALKED, tutoring, type Action, type Beat } from "../wire/index.js";
import { Hearing, captionsOf, keepVisitorChoice, shows, visitorWantsCaptions, type Captions } from "./captions.js";
import { Player } from "./macro.js";
import { Walks } from "./walks.js";
import type { Walked } from "./walking.js";

export interface TutorOptions {
  /** The corner it rests in. Default `right`. */
  dock?: "right" | "left" | undefined;
  /** What the face is called for a screen reader. Default "Talk to the assistant". */
  label?: string | undefined;
  /** The face was clicked: the page starts the call, or ends it. */
  onClick?: (() => void) | undefined;
  /** How long its last words stay beside it after a reply, and the visitor's after theirs, in ms. Default 2600. */
  linger?: number | undefined;
  /** The face's shape: `circle` (the default), `squircle` or `blob`. */
  shape?: Shape | undefined;
  /** The face's and the pointer's colour, any CSS colour; the page's `--pc-face` when left out. */
  color?: string | undefined;
  /** Whose words show: `both` (the default), `agent`, `caller` or `none`. The visitor turns them off and on with CC, unless `none`. */
  captions?: Captions | undefined;
  /** The buttons' names, for a screen reader and a tooltip. Default "Hang up", "Captions", "Explain this", "Walks" and "Stop". */
  words?: {
    hangUp?: string | undefined;
    captions?: string | undefined;
    explain?: string | undefined;
    walks?: string | undefined;
    stop?: string | undefined;
  } | undefined;
  /** Where the agent published its recorded walks (`GET …/v1/agents/{slug}/public/walks`): a button beside the face plays them with no call. */
  walks?: string | undefined;
  /** A walk started, ended, or was stopped: the page's own analytics hear it. */
  onWalk?: ((walked: Walked) => void) | undefined;
}

export interface Tutor {
  /** A message the agent sent on `pinecall.ui`: true when it was the tutor's to carry out, false for a card or choices. */
  take(data: unknown): boolean;
  /** Let the face hear the voice: call it from the click that starts the call. */
  wake(): void;
  close(): void;
}

/** What makes the page worth looking at again, and how long to wait for it to settle, in ms. */
const SETTLE = { scroll: 250, resize: 250, dom: 400, toggle: 150 } as const;

/** Put the tutor on the page, moving with `call`. Nothing is sent until the call is live. */
export function tutor(call: RoomStore, options: TutorOptions = {}): Tutor {
  const document = globalThis.document;
  const view = document.defaultView ?? globalThis.window;
  const still = view.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const page = new Page(document);
  const hover = new Hover(document);
  const captions = captionsOf(options.captions);
  const storage = (): Storage => view.localStorage;
  let captioned = visitorWantsCaptions(storage);
  const person = new Person(document, {
    dock: options.dock ?? "right",
    label: options.label ?? "Talk to the assistant",
    color: options.color,
    onClick: () => (walks.playing ? walks.stop() : options.onClick?.()),
    hangUp: { label: options.words?.hangUp ?? "Hang up", onClick: () => void call.leave() },
    stop: { label: options.words?.stop ?? "Stop", onClick: () => walks.stop() },
    captions:
      captions === "none"
        ? null
        : {
            label: options.words?.captions ?? "Captions",
            onClick: () => {
              captioned = !captioned;
              keepVisitorChoice(storage, captioned);
            },
          },
    explain: { label: options.words?.explain ?? "Explain this", onClick: (element) => send(EXPLAIN, { at: page.refOf(element) }) },
  });
  const drawn = face(person.face, call, { shape: options.shape });
  const inCall = (): boolean => call.state.phase === "opening" || call.state.phase === "live";
  const walks = new Walks(document, person, drawn, {
    dock: options.dock ?? "right",
    label: options.words?.walks ?? "Walks",
    url: options.walks,
    inCall,
    home: () => queue(() => run("home", null)),
    point: (element) => queue(() => run("point", element)),
    onWalk: options.onWalk,
    still,
  });
  const player = new Player();
  const linger = options.linger ?? 2600;
  const hearing = new Hearing(linger);
  let anchor: { element: Element; dx: number; dy: number } | null = null;
  let lit: Element | null = null;
  let flying = false;
  let moves: Promise<void> = Promise.resolve();
  let sent = "";
  let following: string | null = null;
  /** The element with a line under the visitor's mouse, its ▶ shown, while a call is on. */
  let offered: Element | null = null;
  let leaving: ReturnType<typeof setTimeout> | undefined;
  let speech: { id: string; at: number } | null = null;
  let last = { text: "", at: 0 };
  let frame = 0;
  let closed = false;

  const live = (): boolean => call.state.phase === "live";
  const send = (name: string, data: Record<string, unknown>): void => {
    if (live()) void call.event(name, data).catch(() => undefined);
  };
  /** Look at the page again: the refs are fresh, and the agent hears of it when it changed. */
  const look = (why: string): void => {
    const seen = page.seen();
    if (!live() || seen.text === sent) return;
    sent = seen.text;
    send(SEEN, { text: seen.text, why, lines: page.lines() });
    person.face.dataset["pcSeen"] = String(Number(person.face.dataset["pcSeen"] ?? "0") + 1);
  };
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const soon = (why: keyof typeof SETTLE): void => {
    clearTimeout(timers.get(why));
    timers.set(why, setTimeout(() => look(why), SETTLE[why]));
  };

  // The side the face stands on is the destination's, chosen before the flight: chosen on the way, it
  // covered the thing and then jumped clear of it on landing.
  const fly = async (to: Point, side?: Side): Promise<void> => {
    const from = person.at;
    flying = true;
    await animate(still ? 0 : flightMs(Math.hypot(to.x - from.x, to.y - from.y), view.innerWidth), (u) => {
      person.place(along(from, to, u), null, side);
      if (person.touring) person.kind(hover.at(person.at.x, person.at.y));
    });
    flying = false;
  };
  /** What the face must not cover while the pointer is on `element`: on a window of code, the lines lit. */
  const clearOf = (element: Element): DOMRect | null => (element.closest(".pc-code") === null ? null : walks.code.litBox());
  const onScreen = (element: Element): boolean => {
    const box = element.getBoundingClientRect();
    return box.bottom > 0 && box.top < view.innerHeight;
  };
  const run = async (action: Action, element: Element | null): Promise<void> => {
    switch (action) {
      case "type":
        // Typing takes the visitor's words: typeInto, from a cursor move; a macro's beat never types.
        return;
      case "point": {
        if (element === null) return;
        person.tour(true);
        if (!onScreen(element)) await scrollOnto(element, 0.42, still);
        const aim = aimOf(element);
        anchor = null;
        await fly(aim, sideOf(aim, clearOf(element), view.innerWidth, view.innerHeight));
        const box = element.getBoundingClientRect();
        anchor = { element, dx: aim.x - box.left, dy: aim.y - box.top };
        return;
      }
      case "scroll_to":
        if (element === null) return;
        anchor = null;
        await scrollOnto(element, 0.3, still);
        return;
      case "highlight":
        lit = element;
        return;
      case "unhighlight":
        lit = null;
        person.spot(null);
        return;
      case "here":
        person.ring();
        return;
      case "home":
        anchor = null;
        lit = null;
        person.spot(null);
        await fly(person.dock());
        person.tour(false);
        person.kind("arrow");
        hover.clear();
        return;
    }
  };
  /** The pointer onto a field, then the visitor's words typed into it; why it could not, or null. */
  const typeInto = async (element: Element | null, text: string): Promise<string | null> => {
    if (element === null) return null;
    await run("point", element);
    return fill(element, text, still);
  };
  const needsElement = (action: Action): boolean => action === "point" || action === "scroll_to" || action === "highlight" || action === "type";
  /** The ref a target names, a ref or a name, looked at fresh; one not on the page is said, and a fresh look follows. */
  const resolve = (target: string): string | null => {
    look("step");
    const ref = A_REF.test(target) ? target : page.named(target);
    if (ref === null || page.element(ref) === null) {
      send(MISSING, { target });
      sent = "";
      look("missing");
      return null;
    }
    return ref;
  };
  const elementOf = (ref: string | null): Element | null => (ref === null ? null : page.element(ref));
  /** A move onto an element, answered once it ends: the page as it is now, the ref it moved to, and why a field was not filled. */
  const moveOnto = async (action: Action, target: string, text: string): Promise<void> => {
    const ref = resolve(target);
    const element = elementOf(ref);
    let refused: string | null = null;
    if (action === "type") refused = await typeInto(element, text);
    else await run(action, element);
    const seen = page.seen();
    sent = seen.text;
    send(SEEN, { text: seen.text, why: MOVED, lines: page.lines(), ...(ref === null ? {} : { at: ref }), ...(refused === null ? {} : { refused }) });
  };
  const queue = (move: () => Promise<void>): void => {
    moves = moves.then(move).catch(() => undefined);
  };
  const beat = (one: Beat): Promise<void> => {
    if (one.find === undefined) return run(one.do, null);
    look("step");
    const ref = page.find(...one.find);
    return run(one.do, ref === null ? null : elementOf(resolve(ref)));
  };

  const tick = (now: number): void => {
    if (closed) return;
    const walk = walks.frame();
    if (walk !== null) {
      person.say(shows(captions, captioned, "agent", walks.code.open) ? walk.lit : null, walk.coming);
      person.heard(null);
      person.progress(walk.fraction);
      for (const one of walk.beats) queue(() => beat(one));
    } else spoken(now);
    person.buttons(inCall(), walks.playing, captioned);
    // Resting it keeps to its corner; pointing it keeps to its element, which the visitor may scroll.
    if (!flying && !person.touring) person.place(person.dock());
    // An element gone, or hidden (a closed window of code), is let go of where the pointer stands.
    if (anchor !== null && (!anchor.element.isConnected || anchor.element.closest("[hidden]") !== null)) anchor = null;
    if (!flying && anchor !== null) {
      const box = anchor.element.getBoundingClientRect();
      person.place({ x: box.left + anchor.dx, y: box.top + anchor.dy }, clearOf(anchor.element));
      person.kind(hover.at(person.at.x, person.at.y));
    }
    if (lit !== null && !lit.isConnected) lit = null;
    person.spot(lit);
    person.offer(live() && offered?.isConnected === true ? offered : null);
    frame = requestAnimationFrame(tick);
  };

  /** A call's words: the agent's as its voice says them, the visitor's as they say theirs, and the call's macro beats. */
  const spoken = (now: number): void => {
    const saying = sayingOf(call.state.entries);
    if (saying !== null && speech?.id !== saying.speech) speech = { id: saying.speech, at: now };
    let said = "";
    let words: [lit: string, coming: string] | null = null;
    if (saying !== null && saying.words.length > 0 && speech !== null) {
      const split = litAt(saying, now - speech.at);
      said = split.lit;
      last = { text: split.lit + split.coming, at: now };
      words = [split.lit, split.coming];
    }
    const heard = hearing.at(call.state.log, now);
    if (words === null && heard !== null) last = { text: "", at: 0 };
    else if (words === null && last.text !== "" && now - last.at < linger) words = [last.text, ""];
    const agent = shows(captions, captioned, "agent", walks.code.open) ? words : null;
    person.say(agent?.[0] ?? null, agent?.[1] ?? "");
    person.heard(words === null && shows(captions, captioned, "caller", walks.code.open) ? heard : null);
    for (const one of player.due(saying?.speech ?? null, said)) queue(() => beat(one));
  };

  // A page that joins a call tells the agent what it sees, for an agent already in the room (a
  // reload); an agent that arrives after it asks (`look`), since LiveKit keeps no data for whoever
  // joins after it was sent. A call that ends sends the tutor home.
  const unsubscribe = call.subscribe((state) => {
    // A call takes over from a walk; the walks come back when it ends.
    if (inCall()) walks.stop();
    walks.available(!inCall());
    if (state.phase === "live" && state.call !== following) {
      following = state.call;
      sent = "";
      look("joined");
      const played = walks.taken();
      if (played !== null) send(WALKED, { ...played });
    }
    if (state.phase !== "live" && state.phase !== "opening" && (person.touring || player.armed)) {
      player.drop();
      queue(() => run("home", null));
    }
  });

  const onScroll = (): void => soon("scroll");
  const onResize = (): void => soon("resize");
  const onToggle = (): void => soon("toggle");
  // What the visitor types reaches the agent as the page's next look, as their scroll does.
  const onInput = (event: Event): void => {
    if (event.target instanceof Element && event.target.closest("[data-pinecall-skip]") === null) soon("dom");
  };
  // Over the ▶ itself (the tutor's own layer) it stays; off an element with a line it goes a moment later.
  const onOver = (event: PointerEvent): void => {
    const target = event.target instanceof Element ? event.target : null;
    clearTimeout(leaving);
    if (target?.closest("[data-pinecall-skip]") != null) return;
    const marked = target?.closest("[data-pinecall-say]") ?? null;
    if (marked !== null) offered = marked;
    else leaving = setTimeout(() => (offered = null), 400);
  };
  const onClick = (event: MouseEvent): void => {
    const target = event.target instanceof Element ? event.target : null;
    if (target === null || target.closest("[data-pinecall-skip]") !== null) return;
    const clicked = target.closest("a, button, summary, input, select, textarea, [role=button], [role=link]");
    if (clicked === null) return;
    look("click");
    send(CLICKED, { role: clicked.getAttribute("role") ?? clicked.tagName.toLowerCase(), name: (clicked.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80) });
  };
  const changes = new MutationObserver((records) => {
    const ours = (node: Node): boolean => (node instanceof Element ? node : node.parentElement)?.closest("[data-pinecall-skip]") != null;
    if (records.every((record) => ours(record.target))) return;
    soon("dom");
  });
  view.addEventListener("scroll", onScroll, { passive: true });
  view.addEventListener("resize", onResize);
  document.addEventListener("toggle", onToggle, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("input", onInput, true);
  document.addEventListener("pointerover", onOver, true);
  changes.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["open", "hidden", "aria-expanded", "aria-selected", "class"] });
  frame = requestAnimationFrame(tick);

  return {
    take(data) {
      const message = tutoring(data);
      if (message === null) return false;
      if (message.type === "macro.step") {
        player.arm(message, sayingOf(call.state.entries)?.speech ?? null);
        const lit = walks.code.show(message.code, message.lines);
        if (lit !== null) queue(() => run("point", lit));
        return true;
      }
      if (message.type === "macro.done") {
        walks.code.hide();
        return true;
      }
      if (message.type === "look") {
        sent = "";
        look("asked");
        return true;
      }
      const { action, target, text } = message;
      queue(async () => {
        if (needsElement(action) && target !== undefined) await moveOnto(action, target, text ?? "");
        else await run(action, null);
      });
      return true;
    },
    wake() {
      drawn.wake();
    },
    close() {
      if (closed) return;
      closed = true;
      cancelAnimationFrame(frame);
      for (const timer of timers.values()) clearTimeout(timer);
      walks.close();
      clearTimeout(leaving);
      unsubscribe();
      changes.disconnect();
      view.removeEventListener("scroll", onScroll);
      view.removeEventListener("resize", onResize);
      document.removeEventListener("toggle", onToggle, true);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("pointerover", onOver, true);
      drawn.close();
      hover.close();
      person.close();
    },
  };
}
