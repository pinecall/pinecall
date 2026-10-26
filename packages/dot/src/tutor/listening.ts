/** What the tutor hears of the page: a scroll, a resize, a toggle, a field typed in, the page changing, a click, and the mouse over a thing with a line. */
//
// Everything the tutor's own layer does (`data-pinecall-skip`) is left out, so its moves never read as
// the visitor's. The thing with a line under the mouse is kept a moment after the mouse leaves it, so
// its ▶ can be reached.

/** What makes the page worth looking at again. */
export type Why = "scroll" | "resize" | "dom" | "toggle";

export interface Heard {
  /** The page changed for `why`: look again once it settles. */
  soon: (why: Why) => void;
  /** The visitor clicked something a person names: a link, a button, a field. */
  clicked: (element: Element) => void;
}

export interface Listening {
  /** The thing with a line under the visitor's mouse now, or a moment ago. */
  offered(): Element | null;
  close(): void;
}

/** Listen to the page until `close()`. */
export function listen(document: Document, view: Window, heard: Heard): Listening {
  let offered: Element | null = null;
  let leaving: ReturnType<typeof setTimeout> | undefined;
  const ours = (target: EventTarget | null): boolean => target instanceof Element && target.closest("[data-pinecall-skip]") !== null;

  const onScroll = (): void => heard.soon("scroll");
  const onResize = (): void => heard.soon("resize");
  const onToggle = (): void => heard.soon("toggle");
  // What the visitor types reaches the agent as the page's next look, as their scroll does.
  const onInput = (event: Event): void => {
    if (event.target instanceof Element && !ours(event.target)) heard.soon("dom");
  };
  // Over the ▶ itself (the tutor's own layer) it stays; off an element with a line it goes a moment later.
  const onOver = (event: PointerEvent): void => {
    const target = event.target instanceof Element ? event.target : null;
    clearTimeout(leaving);
    if (ours(target)) return;
    const marked = target?.closest("[data-pinecall-say]") ?? null;
    if (marked !== null) offered = marked;
    else leaving = setTimeout(() => (offered = null), 400);
  };
  const onClick = (event: MouseEvent): void => {
    const target = event.target instanceof Element ? event.target : null;
    if (target === null || ours(target)) return;
    const clicked = target.closest("a, button, summary, input, select, textarea, [role=button], [role=link]");
    if (clicked !== null) heard.clicked(clicked);
  };
  const changes = new MutationObserver((records) => {
    if (records.every((record) => ours(record.target instanceof Element ? record.target : record.target.parentElement))) return;
    heard.soon("dom");
  });
  // Captured on the document: a page whose content scrolls in a box of its own is heard scrolling too.
  document.addEventListener("scroll", onScroll, { capture: true, passive: true });
  view.addEventListener("resize", onResize);
  document.addEventListener("toggle", onToggle, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("input", onInput, true);
  document.addEventListener("pointerover", onOver, true);
  changes.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["open", "hidden", "aria-expanded", "aria-selected", "class"] });

  return {
    offered: () => (offered?.isConnected === true ? offered : null),
    close() {
      clearTimeout(leaving);
      changes.disconnect();
      document.removeEventListener("scroll", onScroll, true);
      view.removeEventListener("resize", onResize);
      document.removeEventListener("toggle", onToggle, true);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("pointerover", onOver, true);
    },
  };
}
