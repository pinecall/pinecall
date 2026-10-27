/** A frame of the site's own (same origin) as the pointer sees it: where its elements stand on the page's screen, and the documents it holds. */
//
// The pointer lives on the top page. An element in a frame the site serves itself (a chat, a widget) is
// measured on the frame's own screen; its box is moved by every frame it stands in, so the pointer flies to
// it, the light falls on it and the page scrolls to it as to any other. A frame of another origin is closed
// to the page, and so to the pointer. An element of a frame is of the frame's window, not the page's, so
// it is told by its tag, never by `instanceof`.

/** A box on the top page's screen. */
export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

/** The frame `document` is shown in, or null for the top page (or a frame whose page is closed to this one). */
export function frameOf(document: Document): Element | null {
  const view = document.defaultView;
  if (view === null) return null;
  try {
    if (view.frameElement != null) return view.frameElement;
    // A window that does not say (a test's): the frame, on the page around it, whose page this is.
    if (view.parent === view) return null;
    return [...view.parent.document.querySelectorAll("iframe")].find((frame) => pageOf(frame) === document) ?? null;
  } catch {
    return null;
  }
}

/** The page a frame shows, when it is the site's own and loaded; null for another origin's, or none yet. */
export function pageOf(frame: Element): Document | null {
  try {
    const page = (frame as HTMLIFrameElement).contentDocument;
    return page?.body != null ? page : null;
  } catch {
    return null;
  }
}

/** Where `document`'s screen starts on the top page's. */
export function originOf(document: Document): { x: number; y: number } {
  let x = 0;
  let y = 0;
  for (let frame = frameOf(document); frame !== null; frame = frameOf(frame.ownerDocument)) {
    const box = frame.getBoundingClientRect();
    x += box.left + frame.clientLeft;
    y += box.top + frame.clientTop;
  }
  return { x, y };
}

/** A box of `document`'s screen, on the top page's. */
export function onTop(box: Box, document: Document): Box {
  const { x, y } = originOf(document);
  return { left: box.left + x, top: box.top + y, right: box.right + x, bottom: box.bottom + y, width: box.width, height: box.height };
}

/** `element`'s box on the top page's screen. */
export function boxOf(element: Element): Box {
  return onTop(element.getBoundingClientRect(), element.ownerDocument);
}

/** The pages of the site's own frames inside `root`, in order; a frame of another origin, or not loaded, is left out. */
export function framesIn(root: ParentNode): Document[] {
  return [...root.querySelectorAll("iframe")].flatMap((frame) => {
    const page = pageOf(frame);
    return page === null ? [] : [page];
  });
}

/** Whether `node` is an element, in any window. */
export function isElement(node: Node | null | undefined): node is Element {
  return node != null && node.nodeType === 1;
}
