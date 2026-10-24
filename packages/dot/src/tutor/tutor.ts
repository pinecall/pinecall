/** The tutor on a page: the person with its pointer and face, what it sends of the page, and every move the agent asks for. */
//
// Up, as events on the call: the page as it is now (`page.seen`, when it changed, and when a move
// onto an element ended, with the ref it moved to), what the visitor clicked, a ref that is gone.
// Down, from `pinecall.ui`: a cursor move, run at once, or a macro's step, whose moves run on their
// words. Moves run one after another, so a scroll ends before the point that follows it. In words,
// one side at a time: the visitor's as they say them, else the agent's as its voice says them.

import { litAt, sayingOf, type RoomStore } from "@pinecall/room";

import { face } from "../face/index.js";
import { Page } from "../page/page.js";
import { aimOf, along, animate, flightMs, scrollOnto, type Point } from "../pointer/flight.js";
import { Hover } from "../pointer/hover.js";
import { Person } from "../pointer/person.js";
import { A_REF, CLICKED, MISSING, MOVED, SEEN, tutoring, type Action, type Beat } from "../wire/index.js";
import { Hearing, captionsOf, keepVisitorChoice, shows, visitorWantsCaptions, type Captions } from "./captions.js";
import { Player } from "./macro.js";

export interface TutorOptions {
  /** The corner it rests in. Default `right`. */
  dock?: "right" | "left" | undefined;
  /** What the face is called for a screen reader. Default "Talk to the assistant". */
  label?: string | undefined;
  /** The face was clicked: the page starts the call, or ends it. */
  onClick?: (() => void) | undefined;
  /** How long its last words stay beside it after a reply, and the visitor's after theirs, in ms. Default 2600. */
  linger?: number | undefined;
  /** Whose words show: `both` (the default), `agent`, `caller` or `none`. The visitor turns them off and on with CC, unless `none`. */
  captions?: Captions | undefined;
  /** The buttons' names, for a screen reader and a tooltip. Default "Hang up" and "Captions". */
  words?: { hangUp?: string | undefined; captions?: string | undefined } | undefined;
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
    onClick: () => options.onClick?.(),
    hangUp: { label: options.words?.hangUp ?? "Hang up", onClick: () => void call.leave() },
    captions:
      captions === "none"
        ? null
        : {
            label: options.words?.captions ?? "Captions",
            onClick: () => {
              captioned = !captioned;
              keepVisitorChoice(storage, captioned);
              person.calling(true, captioned);
            },
          },
  });
  const drawn = face(person.face, call);
  const player = new Player();
  const linger = options.linger ?? 2600;
  const hearing = new Hearing(linger);
  let anchor: { element: Element; dx: number; dy: number } | null = null;
  let lit: Element | null = null;
  let flying = false;
  let moves: Promise<void> = Promise.resolve();
  let sent = "";
  let following: string | null = null;
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
    send(SEEN, { text: seen.text, why });
    person.face.dataset["pcSeen"] = String(Number(person.face.dataset["pcSeen"] ?? "0") + 1);
  };
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const soon = (why: keyof typeof SETTLE): void => {
    clearTimeout(timers.get(why));
    timers.set(why, setTimeout(() => look(why), SETTLE[why]));
  };

  const fly = async (to: Point): Promise<void> => {
    const from = person.at;
    flying = true;
    await animate(still ? 0 : flightMs(Math.hypot(to.x - from.x, to.y - from.y), view.innerWidth), (u) => {
      person.place(along(from, to, u));
      if (person.touring) person.kind(hover.at(person.at.x, person.at.y));
    });
    flying = false;
  };
  const onScreen = (element: Element): boolean => {
    const box = element.getBoundingClientRect();
    return box.bottom > 0 && box.top < view.innerHeight;
  };
  const run = async (action: Action, element: Element | null): Promise<void> => {
    switch (action) {
      case "point": {
        if (element === null) return;
        person.tour(true);
        if (!onScreen(element)) await scrollOnto(element, 0.42, still);
        const aim = aimOf(element);
        anchor = null;
        await fly(aim);
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
  const needsElement = (action: Action): boolean => action === "point" || action === "scroll_to" || action === "highlight";
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
  /** A move onto an element, answered once it ends: the page as it is now, and the ref it moved to. */
  const moveOnto = async (action: Action, target: string): Promise<void> => {
    const ref = resolve(target);
    await run(action, elementOf(ref));
    const seen = page.seen();
    sent = seen.text;
    send(SEEN, { text: seen.text, why: MOVED, ...(ref === null ? {} : { at: ref }) });
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
    const agent = shows(captions, captioned, "agent") ? words : null;
    person.say(agent?.[0] ?? null, agent?.[1] ?? "");
    person.heard(words === null && shows(captions, captioned, "caller") ? heard : null);
    for (const one of player.due(saying?.speech ?? null, said)) queue(() => beat(one));
    // Resting it keeps to its corner; pointing it keeps to its element, which the visitor may scroll.
    if (!flying && !person.touring) person.place(person.dock());
    if (!flying && anchor !== null && anchor.element.isConnected) {
      const box = anchor.element.getBoundingClientRect();
      person.place({ x: box.left + anchor.dx, y: box.top + anchor.dy });
      person.kind(hover.at(person.at.x, person.at.y));
    }
    if (lit !== null && !lit.isConnected) lit = null;
    person.spot(lit);
    frame = requestAnimationFrame(tick);
  };

  // A page that joins a call tells the agent what it sees, for an agent already in the room (a
  // reload); an agent that arrives after it asks (`look`), since LiveKit keeps no data for whoever
  // joins after it was sent. A call that ends sends the tutor home.
  const unsubscribe = call.subscribe((state) => {
    person.calling(state.phase === "opening" || state.phase === "live", captioned);
    if (state.phase === "live" && state.call !== following) {
      following = state.call;
      sent = "";
      look("joined");
    }
    if (state.phase !== "live" && state.phase !== "opening" && (person.touring || player.armed)) {
      player.drop();
      queue(() => run("home", null));
    }
  });

  const onScroll = (): void => soon("scroll");
  const onResize = (): void => soon("resize");
  const onToggle = (): void => soon("toggle");
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
  changes.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["open", "hidden", "aria-expanded", "aria-selected", "class"] });
  frame = requestAnimationFrame(tick);

  return {
    take(data) {
      const message = tutoring(data);
      if (message === null) return false;
      if (message.type === "macro.step") {
        player.arm(message, sayingOf(call.state.entries)?.speech ?? null);
        return true;
      }
      if (message.type === "look") {
        sent = "";
        look("asked");
        return true;
      }
      const { action, target } = message;
      queue(() => (needsElement(action) && target !== undefined ? moveOnto(action, target) : run(action, null)));
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
      unsubscribe();
      changes.disconnect();
      view.removeEventListener("scroll", onScroll);
      view.removeEventListener("resize", onResize);
      document.removeEventListener("toggle", onToggle, true);
      document.removeEventListener("click", onClick, true);
      drawn.close();
      hover.close();
      person.close();
    },
  };
}
