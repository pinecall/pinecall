/** The pointer filling a field the way a person types: letter by letter, with the events the site's own code listens for. */
//
// The value is set through the element's own setter and announced with `input` and `change`, so a
// framework that watches the field (React's, Vue's) sees it typed. A list takes the option whose
// words hold what was said. It never submits, and never touches a password, a card, a file or a
// hidden field.

/** How long one letter takes, in ms. */
const LETTER_MS = 45;
/** The inputs a person writes words in. */
const WRITTEN = new Set(["text", "tel", "email", "search", "url", "number", "date", "time", "datetime-local", "month", "week"]);

/** Why `element` is not a field to fill, or null when it is one. */
export function notFillable(element: Element): string | null {
  if (element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) return element.disabled ? "it is disabled" : null;
  if (!(element instanceof HTMLInputElement)) return "it is not a field";
  if (element.type === "password" || element.autocomplete.startsWith("cc-")) return "a password or a card is the visitor's to type";
  if (!WRITTEN.has(element.type)) return `a ${element.type} field is not written in`;
  return element.disabled || element.readOnly ? "it is disabled" : null;
}

/** Fill `field` with `text`: typed letter by letter, or, for a list, the option that says it. Resolves with why it could not, or null. */
export async function fill(field: Element, text: string, still: boolean): Promise<string | null> {
  const refused = notFillable(field);
  if (refused !== null) return refused;
  if (field instanceof HTMLSelectElement) return choose(field, text);
  const written = field as HTMLInputElement | HTMLTextAreaElement;
  written.focus({ preventScroll: true });
  if (still) {
    set(written, text);
  } else {
    set(written, "");
    for (let at = 1; at <= text.length; at++) {
      set(written, text.slice(0, at));
      await new Promise((done) => setTimeout(done, LETTER_MS));
    }
  }
  written.dispatchEvent(new Event("change", { bubbles: true }));
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

// A framework keeps its own copy of the value and reads it back from the prototype's setter.
function set(field: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}
