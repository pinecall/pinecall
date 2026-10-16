/** Where the agent's voice plays: a hidden element in the page, made the first time it is needed. */

/** What the seat hands a voice to. A test hands in one that records instead of playing. */
export interface Sink {
  add(element: HTMLMediaElement): void;
  remove(element: HTMLMediaElement): void;
  /** Every element out of the page. */
  close(): void;
}

/** A hidden box at the end of the body. Nothing touches the document until a voice arrives. */
export function hiddenSink(): Sink {
  let box: HTMLElement | null = null;
  return {
    add(element) {
      if (box === null) {
        box = document.createElement("div");
        box.style.display = "none";
        document.body.append(box);
      }
      box.append(element);
    },
    remove(element) {
      element.remove();
    },
    close() {
      box?.remove();
      box = null;
    },
  };
}
