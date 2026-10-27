/** The pointer filling a field the way a person types: letter by letter, with the events the site's own code listens for. */
//
// The value is set through the element's own setter and announced with `input` and `change`, so a
// framework that watches the field (React's, Vue's) sees it typed. A list takes the option whose
// words hold what was said. It never submits, and never touches a password, a card, a file or a
// hidden field.

/** How long one letter takes, in ms. */
const LETTER_MS = 45;
/** The slowest a letter comes when the typing is paced to a recording, in ms: a long sentence over a few words typed. */
const SLOWEST_MS = 180;
/** The event an element that is no field is typed into by: the site's own editor takes each with `preventDefault()` and writes `detail.text`, what was typed so far, where it belongs; `detail.done` on the last. */
export const TYPING_EVENT = "pinecall-typing";
const NOT_A_FIELD = "it is not a field";
/** The inputs a person writes words in. */
const WRITTEN = new Set(["text", "tel", "email", "search", "url", "number", "date", "time", "datetime-local", "month", "week"]);

/** Why `element` is not a field to fill, or null when it is one. Told by its tag: a frame's field is of the frame's window. */
export function notFillable(element: Element): string | null {
  if (element.tagName === "SELECT" || element.tagName === "TEXTAREA") return (element as HTMLTextAreaElement).disabled ? "it is disabled" : null;
  if (element.tagName !== "INPUT") return NOT_A_FIELD;
  const input = element as HTMLInputElement;
  if (input.type === "password" || input.autocomplete.startsWith("cc-")) return "a password or a card is the visitor's to type";
  if (!WRITTEN.has(input.type)) return `a ${input.type} field is not written in`;
  return input.disabled || input.readOnly ? "it is disabled" : null;
}

/** Fill `field` with `text`: typed letter by letter (paced to `ms`, a recording said meanwhile), or, for a list, the option that says it; an element that is no field, by `TYPING_EVENT`s the site takes. Resolves with why it could not, or null. */
export async function fill(field: Element, text: string, still: boolean, ms?: number): Promise<string | null> {
  const refused = notFillable(field);
  if (refused === NOT_A_FIELD) return told(field, text, still, ms);
  if (refused !== null) return refused;
  if (field.tagName === "SELECT") return choose(field as HTMLSelectElement, text);
  const written = field as HTMLInputElement | HTMLTextAreaElement;
  written.focus({ preventScroll: true });
  if (still) {
    set(written, text);
  } else {
    set(written, "");
    for (let at = 1; at <= text.length; at++) {
      set(written, text.slice(0, at));
      await new Promise((done) => setTimeout(done, paceOf(text, ms)));
    }
  }
  written.dispatchEvent(new Event("change", { bubbles: true }));
  return null;
}

/** How long each letter takes: `LETTER_MS`, or the recording's length spread over the letters, `SLOWEST_MS` at most. */
function paceOf(text: string, ms?: number): number {
  return ms === undefined ? LETTER_MS : Math.min(SLOWEST_MS, Math.max(LETTER_MS / 2, (ms * 0.9) / Math.max(1, text.length)));
}

// An element that is no field is told what is typed, a letter at a time, and the site writes it where it
// belongs (its editor); an element whose site takes no such event is no place to type.
async function told(element: Element, text: string, still: boolean, ms?: number): Promise<string | null> {
  const taken = (typed: string, done: boolean): boolean =>
    !element.dispatchEvent(new CustomEvent(TYPING_EVENT, { bubbles: true, cancelable: true, detail: { text: typed, done } }));
  (element as HTMLElement).focus?.({ preventScroll: true });
  if (still) return taken(text, true) ? null : NOT_A_FIELD;
  if (!taken("", false)) return NOT_A_FIELD;
  for (let at = 1; at <= text.length; at++) {
    taken(text.slice(0, at), at === text.length);
    await new Promise((done) => setTimeout(done, paceOf(text, ms)));
  }
  return null;
}

function choose(list: HTMLSelectElement, text: string): string | null {
  const wanted = text.trim().toLowerCase();
  const options = [...list.options];
  const option = options.find((one) => one.text.trim().toLowerCase() === wanted) ?? options.find((one) => one.text.toLowerCase().includes(wanted));
  if (option === undefined) return `no option says "${text}": the options are ${options.map((one) => `"${one.text}"`).join(", ")}`;
  list.value = option.value;
  list.dispatchEvent(new Event("input", { bubbles: true }));
  list.dispatchEvent(new Event("change", { bubbles: true }));
  return null;
}

// A framework keeps its own copy of the value and reads it back from the prototype's setter: the one of the
// field's own window, found up its chain.
function set(field: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  let prototype = Object.getPrototypeOf(field) as object | null;
  while (prototype !== null && Object.getOwnPropertyDescriptor(prototype, "value") === undefined) prototype = Object.getPrototypeOf(prototype) as object | null;
  if (prototype !== null) Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}
