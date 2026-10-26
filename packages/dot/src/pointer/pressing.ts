/** The pointer pressing a button a walk names: a search, a tab, a "show more", never a form that sends the visitor's details. */
//
// A walk the site wrote may press a button by its name, as a person would: the click the site's own code
// listens for. Not one in a form, unless the form is a search (`<search>`, `role="search"`): a form that
// books, buys or signs up is the visitor's to send. Not a link, which leaves the page, and not a button
// that is disabled or hidden.

/** Why `element` is not a button the pointer presses, or null when it is one. */
export function notPressable(element: Element): string | null {
  const button = element.closest("button, input[type=submit], input[type=button], [role=button]");
  if (button === null || !(button instanceof HTMLElement)) return "it is not a button";
  if (button.closest("a[href]") !== null) return "it leaves the page";
  if ((button instanceof HTMLButtonElement || button instanceof HTMLInputElement) && button.disabled) return "it is disabled";
  if (button.getAttribute("aria-disabled") === "true") return "it is disabled";
  if (button.closest("form") !== null && button.closest("search, [role=search]") === null) return "it sends a form, which is the visitor's to send";
  return null;
}

/** Press `element`: the click a person makes. Resolves with why it could not, or null. */
export function press(element: Element): string | null {
  const refused = notPressable(element);
  if (refused !== null) return refused;
  const button = element.closest("button, input[type=submit], input[type=button], [role=button]") as HTMLElement;
  button.click();
  return null;
}
