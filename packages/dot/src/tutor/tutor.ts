/** The tutor on a page: the person with its pointer and face, what it sends of the page, and every move the agent asks for. */
//
// Up, as events on the call: the page as it is now (`page.seen`, when it changed, and when a move
// onto an element ended, with the ref it moved to), what the visitor clicked, a ref that is gone.
// Down, from `pinecall.ui`: a cursor move, run at once, or a macro's step, whose moves run on their
// words. Moves run one after another, so a scroll ends before the point that follows it. In words,
// one side at a time: the visitor's as they say them, else the agent's as its voice says them.
// With no call, the walks the agent published play from a button beside the face (`walks`); a walk's
// acts (fill, press, wait, read) are done here, on the same queue as the moves (`acting.ts`).

import { litAt, sayingOf, type RoomStore } from "@pinecall/room";

import { face } from "../face/index.js";
import { Page } from "../page/page.js";
import { aimOf, along, animate, besideOf, coveredTop, flightMs, scrollOnto, shownWhole, type Point } from "../pointer/flight.js";
import { Card } from "../pointer/card.js";
import { Hover } from "../pointer/hover.js";
import { Person, sideOf, type Side } from "../pointer/person.js";
import { fill } from "../pointer/typing.js";
import { A_REF, CLICKED, EXPLAIN, MISSING, MOVED, SEEN, WALKED, tutoring, type Action, type Beat } from "../wire/index.js";
import { Acting, WAIT_MS } from "./acting.js";
import { Hearing, captionsOf, keepVisitorChoice, shows, visitorWantsCaptions } from "./captions.js";
import { act, askWords, type Asked } from "./ask.js";
import { listen } from "./listening.js";
import { readingWith } from "./reading.js";
import { Player } from "./macro.js";
import type { TutorOptions } from "./options.js";
import { Screen } from "./views.js";
import { Walks } from "./walks.js";

export type { TutorOptions } from "./options.js";

export interface Tutor {
  /** A message the agent sent on `pinecall.ui`: true when it was the tutor's to carry out, false for a card or choices. */
  take(data: unknown): boolean;
  /** Let the face hear the voice: call it from the click that starts the call. */
  wake(): void;
  /** Read the page aloud (`reading`), from the visitor's click: a button of the site's own. */
  read(): void;
  close(): void;
}

/** How long what the visitor asked for stays shown, its name beside the face, in ms. */
const NOTE_MS = 6000;

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
    pause: { label: options.words?.pause ?? "Pause", onClick: () => walks.pause() },
    back: { label: options.words?.back ?? "Back", onClick: () => walks.skip(-1) },
    next: { label: options.words?.next ?? "Next", onClick: () => walks.skip(1) },
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
  const acting = new Acting({
    document, page, door: options.ask, queued: (work) => queued(work), point: (element) => run("point", element),
    ring: () => person.ring(), type: (element, text) => typeInto(element, text),
  });
  const walks = new Walks(document, person, drawn, {
    dock: options.dock ?? "right",
    label: options.words?.walks ?? "Walks",
    more: options.words?.more ?? "More walks",
    url: options.walks,
    inCall,
    home: () => queue(() => run("home", null)),
    point: (element) => queue(() => run("point", element)),
    onWalk: options.onWalk,
    still,
    ask: options.ask && options.typing !== false ? { placeholder: options.words?.ask ?? "Ask me to show you…", onAsk: (text) => asked && void act(text, asked) } : undefined,
    act: (step, values, message) => acting.act(step, values, message),
    voice: (walk, at, values) => acting.voice(view.location.pathname, walk, at, values),
    reading: options.reading === undefined || options.ask === undefined ? undefined : readingWith(options.reading, acting, document, {
      // The part read is lit (every frame spots `lit`) and pointed at; null puts the light out.
      light: (element) => queue(async () => {
        lit = element;
        if (element !== null) await run("point", element, true);
      }),
      queued: (work) => queued(work),
    }),
  });
  // What the visitor typed to the dot: a walk played, or a thing lit and pointed at with its name beside the face for a moment.
  let note: { text: string; until: number } | null = null;
  let showing = 0;
  const asked: Asked | null = options.ask === undefined ? null : {
    ask: options.ask, page, path: () => view.location.pathname, walks: () => walks.listed(), unlock: () => walks.unlock(),
    play: (name, values, message) => walks.playNamed(name, values, message),
    show: (element, role, name) => {
      const mine = (showing += 1);
      if (["region", "article", "group", "form"].includes(role)) queue(() => run("highlight", element));
      queue(() => run("point", element));
      note = { text: name, until: performance.now() + NOTE_MS };
      setTimeout(() => mine === showing && queue(() => run("home", null)), NOTE_MS);
    },
    note: (text) => void (note = text === null ? null : { text, until: performance.now() + NOTE_MS }),
    offer: (text, action) => walks.offer(text, action), talk: options.onTalk, words: askWords(options.words),
  };
  const screen = new Screen(call, new Card(document, (part) => person.add(part), options.words?.close ?? "Close"), () => options.views);
  const player = new Player();
  const linger = options.linger ?? 2600;
  const hearing = new Hearing(linger);
  let anchor: { element: Element; dx: number; dy: number; side?: Side | undefined } | null = null;
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
    send(SEEN, { text: seen.text, why, lines: page.lines(), path: view.location.pathname });
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
    // Under the site's own header is not on the screen: the visitor cannot see it.
    const box = element.getBoundingClientRect();
    return box.bottom > coveredTop(document) && box.top < view.innerHeight;
  };
  /** A move; `beside`, a block being read pointed at from its left, the face in the margin, never on its words. */
  const run = async (action: Action, element: Element | null, beside = false): Promise<void> => {
    switch (action) {
      case "type":
      case "press":
      case "wait":
        // Typing takes the visitor's words, pressing and waiting a step of their own (moveOnto, a walk's acts): a beat never does them.
        return;
      case "point": {
        if (element === null) return;
        person.tour(true);
        // Let go of what it pointed at before the page scrolls: held, the face rode off the screen with it.
        anchor = null;
        if (beside ? !shownWhole(element) : !onScreen(element)) await scrollOnto(element, 0.42, still);
        // A box the page scrolls in some other way (a pane this did not find): the browser's own scroll, at once.
        if (beside && !shownWhole(element)) element.scrollIntoView({ block: "start" });
        const { aim, side } = beside ? besideOf(element) : { aim: aimOf(element), side: undefined };
        await fly(aim, side ?? sideOf(aim, clearOf(element), view.innerWidth, view.innerHeight));
        const box = element.getBoundingClientRect();
        anchor = { element, dx: aim.x - box.left, dy: aim.y - box.top, side };
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
  const needsElement = (action: Action): boolean => action !== "unhighlight" && action !== "here" && action !== "home";
  /** The ref a target names, a ref or a name (of one of `roles`), looked at fresh; one not on the page is said, and a fresh look follows. */
  const resolve = (target: string, roles?: readonly string[]): string | null => {
    look("step");
    const ref = A_REF.test(target) ? target : page.named(target, roles);
    if (ref === null || page.element(ref) === null) {
      send(MISSING, { target });
      sent = "";
      look("missing");
      return null;
    }
    return ref;
  };
  const elementOf = (ref: string | null): Element | null => (ref === null ? null : page.element(ref));
  /** A move onto an element, answered once it ends: the page as it is now, the ref it moved to, and why a field was not filled or a button not pressed. */
  const moveOnto = async (action: Action, target: string, text: string, ms = WAIT_MS): Promise<void> => {
    const ref = resolve(target, action === "press" ? ["button"] : undefined);
    const element = elementOf(ref);
    let refused: string | null = null;
    if (action === "type") refused = await typeInto(element, text);
    else if (action === "press") refused = element === null ? null : await acting.press(element);
    else if (action === "wait") await acting.wait(() => elementOf(ref), ms);
    else await run(action, element);
    const seen = page.seen();
    sent = seen.text;
    send(SEEN, { text: seen.text, why: MOVED, lines: page.lines(), ...(ref === null ? {} : { at: ref }), ...(refused === null ? {} : { refused }) });
  };
  const queue = (move: () => Promise<void>): void => {
    moves = moves.then(move).catch(() => undefined);
  };
  /** Work after the moves already queued, its result handed back. */
  const queued = <T>(work: () => Promise<T>): Promise<T> => {
    const done = moves.then(work);
    moves = done.then(() => undefined, () => undefined);
    return done;
  };
  const beat = (one: Beat): Promise<void> => {
    if (one.find === undefined) return run(one.do, null);
    look("step");
    // On the screen first; a row a walk read may be below it.
    const ref = page.find(...one.find) ?? page.named(one.find[1], [one.find[0]]);
    return run(one.do, ref === null ? null : elementOf(resolve(ref)));
  };

  const tick = (now: number): void => {
    if (closed) return;
    const walk = walks.frame();
    if (walk !== null) {
      person.say(shows(captions, captioned, "agent", walks.code.open || screen.shown) ? walk.lit : null, walk.coming);
      person.heard(null);
      person.progress(walk.fraction);
      for (const one of walk.beats) queue(() => beat(one));
    } else if (note !== null && now < note.until && !inCall()) {
      person.say(note.text);
      person.heard(null);
    } else spoken(now);
    person.buttons(inCall(), walks.playing, captioned, walks.paused);
    walks.place();
    // Resting it keeps to its corner; pointing it keeps to its element, which the visitor may scroll.
    if (!flying && !person.touring) person.place(person.dock());
    // An element gone, or hidden (a closed window of code), is let go of where the pointer stands.
    if (anchor !== null && (!anchor.element.isConnected || anchor.element.closest("[hidden]") !== null)) anchor = null;
    if (!flying && anchor !== null) {
      const box = anchor.element.getBoundingClientRect();
      person.place({ x: box.left + anchor.dx, y: box.top + anchor.dy }, clearOf(anchor.element), anchor.side);
      person.kind(hover.on(anchor.element));
    }
    if (lit !== null && !lit.isConnected) lit = null;
    person.spot(lit);
    person.offer(live() ? listening.offered() : null);
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
    const agent = shows(captions, captioned, "agent", walks.code.open || screen.shown) ? words : null;
    person.say(agent?.[0] ?? null, agent?.[1] ?? "");
    person.heard(words === null && shows(captions, captioned, "caller", walks.code.open || screen.shown) ? heard : null);
    for (const one of player.due(saying?.speech ?? null, said)) queue(() => beat(one));
  };

  // A page that joins a call tells the agent what it sees, for an agent already in the room (a
  // reload); an agent that arrives after it asks (`look`), since LiveKit keeps no data for whoever
  // joins after it was sent. A call that ends sends the tutor home.
  const unsubscribe = call.subscribe((state) => {
    screen.update(state);
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

  const listening = listen(document, view, {
    soon,
    clicked: (clicked) => {
      look("click");
      send(CLICKED, { role: clicked.getAttribute("role") ?? clicked.tagName.toLowerCase(), name: (clicked.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80) });
    },
  });
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
      const { action, target, text, ms } = message;
      queue(async () => {
        if (needsElement(action) && target !== undefined) await moveOnto(action, target, text ?? "", ms);
        else await run(action, null);
      });
      return true;
    },
    wake() {
      drawn.wake();
    },
    read() {
      walks.read();
    },
    close() {
      if (closed) return;
      closed = true;
      cancelAnimationFrame(frame);
      for (const timer of timers.values()) clearTimeout(timer);
      walks.close();
      acting.close();
      screen.close();
      unsubscribe();
      listening.close();
      drawn.close();
      hover.close();
      person.close();
    },
  };
}
