/** What an element is to a person, as the accessibility tree says it: its role and its name. */

/** The role an element plays: its `role`, else the one its tag implies; null for a box that is only layout. */
export function roleOf(element: Element): string | null {
  const explicit = element.getAttribute("role");
  if (explicit) return explicit;
  const tag = element.tagName.toLowerCase();
  if (tag === "a" && element.hasAttribute("href")) return "link";
  if (tag === "button" || tag === "summary") return "button";
  if (/^h[1-6]$/.test(tag)) return "heading";
  if (tag === "nav") return "navigation";
  if (tag === "header" && element.closest("main, article, section") === null) return "banner";
  if (tag === "footer" && element.closest("main, article, section") === null) return "contentinfo";
  if (tag === "main") return "main";
  if (tag === "section" && (element.hasAttribute("aria-labelledby") || element.hasAttribute("aria-label"))) return "region";
  if (tag === "article") return "article";
  if (tag === "form") return "form";
  if (tag === "select") return "combobox";
  if (tag === "textarea") return "textbox";
  if (tag === "input") return inputRole(element);
  if (tag === "img" || tag === "figure") return "img";
  if (tag === "ul" || tag === "ol") return "list";
  if (tag === "li") return "listitem";
  if (tag === "details") return "group";
  if (tag === "p") return "text";
  return null;
}

function inputRole(input: Element): string {
  const type = (input.getAttribute("type") ?? "text").toLowerCase();
  if (type === "checkbox" || type === "radio") return type;
  if (type === "submit" || type === "button") return "button";
  return "textbox";
}

/** Text on one line, cut at `max` characters. */
export function clean(text: string | null | undefined, max = 80): string {
  const line = (text ?? "").replace(/\s+/g, " ").trim();
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

/** The roles whose name is their own words: nothing under them is said again. */
export const SAID_WHOLE = new Set(["link", "button", "tab", "heading", "text", "textbox", "combobox", "listitem"]);

/** What a person calls the element. A field is its label, never its value: a value never leaves the page. */
export function nameOf(element: Element, role: string): string {
  const label = element.getAttribute("aria-label");
  if (label) return clean(label);
  const by = element.getAttribute("aria-labelledby");
  if (by) return clean(by.split(/\s+/).map((id) => element.ownerDocument.getElementById(id)?.textContent ?? "").join(" "));
  if (role === "img") return clean(element.getAttribute("alt") ?? element.textContent);
  if (role === "textbox" || role === "combobox") return fieldLabel(element);
  if (SAID_WHOLE.has(role)) return clean(element.textContent, role === "text" ? 120 : 80);
  return "";
}

// The label's own words, without the field inside it: a <label> that wraps its input holds the value too.
function fieldLabel(field: Element): string {
  const id = field.getAttribute("id");
  const label = id ? field.ownerDocument.querySelector(`label[for="${CSS.escape(id)}"]`) : field.closest("label");
  if (label !== null) {
    const words = [...label.childNodes].filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent ?? "");
    return clean(words.join(" "));
  }
  return clean(field.getAttribute("placeholder"));
}
