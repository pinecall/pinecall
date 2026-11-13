// The header's menu in <pinecall-widget>'s panel. The header keeps the two things a visitor reaches
// for, the call and the close; what she does now and then is behind one button: a new conversation,
// the ones before, the theme, the panel's size. Each item is the button it always was, with its
// words beside its icon, so whatever shows or hides one (a page that forced the theme, a phone, no
// conversation kept) goes on doing so.

export class Menu {
  constructor(widget) {
    this.widget = widget;
    this.more = widget.$(".more");
    this.list = widget.$(".menu");
    this.more.addEventListener("click", () => (this.list.hidden ? this.show() : this.hide()));
    // An item does what it does, and the menu steps aside.
    this.list.addEventListener("click", () => this.hide());
    widget.shadowRoot.addEventListener("pointerdown", (event) => {
      if (!this.list.hidden && !event.composedPath().some((node) => node === this.list || node === this.more)) this.hide();
    });
    widget.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || this.list.hidden) return;
      // The menu closes and nothing else does: Escape under it would also restore a maximized panel.
      event.stopImmediatePropagation();
      this.hide();
      this.more.focus();
    });
  }

  /** One item's icon and its words: `item(".theme", ICONS.moon, "Dark theme")`. */
  item(selector, icon, words) {
    const button = this.widget.$(selector);
    button.querySelector(".ico").innerHTML = icon;
    button.querySelector(".name").textContent = words;
  }

  show() {
    this.list.hidden = false;
    this.more.ariaExpanded = "true";
    this.list.querySelector(".item:not([hidden])")?.focus();
  }

  hide() {
    this.list.hidden = true;
    this.more.ariaExpanded = "false";
  }
}
