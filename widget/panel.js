// The frame of <pinecall-widget>'s panel: the size the visitor drags it to and keeps, maximized from
// the header, exactly the visible part of the screen on a phone, the page held still while the panel
// covers it, and the theme the visitor switches to when the page left it to them.

import { ICONS } from "./markup.js";
import { PHONE } from "./styles.js";

// The smallest a visitor can drag the panel to, in px.
const PANEL_AT_LEAST = { width: 320, height: 420 };

/** Read a kept setting; storage may be unavailable, and then nothing was kept. */
function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Keep a setting, or forget it with null; storage unavailable, it holds for this page alone. */
function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // storage unavailable
  }
}

export class Panel {
  constructor(widget) {
    this.widget = widget;
    this.panel = widget.$(".panel");
    this.sizeKey = `pinecall-widget:size:${widget.agent}`;
    this.themeKey = `pinecall-widget:theme:${widget.agent}`;
    this.fitting = null;
    this.heldAt = undefined;
    this.bodyWas = null;
  }

  // ── size and place ─────────────────────────────────────────────────────────────

  /** The kept size, the maximize button and Escape, and the edges that drag. */
  sizing() {
    const panel = this.panel;
    const apply = (size) => {
      panel.classList.toggle("sized", Boolean(size));
      if (size) {
        panel.style.setProperty("--_w", `${size.width}px`);
        panel.style.setProperty("--_h", `${size.height}px`);
      }
    };
    const keep = (size) => write(this.sizeKey, size ? JSON.stringify(size) : null);
    try {
      const size = JSON.parse(read(this.sizeKey) ?? "null");
      if (size && size.width >= PANEL_AT_LEAST.width && size.height >= PANEL_AT_LEAST.height) apply(size);
    } catch {
      // a size this browser kept badly: the panel opens at its own
    }
    this.widget.$(".maximize").addEventListener("click", () => {
      panel.classList.toggle("maxed");
      this.label();
      this.hold();
    });
    this.widget.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && panel.classList.contains("maxed")) {
        panel.classList.remove("maxed");
        this.label();
        this.hold();
      }
    });
    // The edges face the page's middle: dragged toward it, the panel grows.
    const position = this.widget.getAttribute("position") ?? "bottom-right";
    const toward = { x: position.endsWith("left") ? 1 : -1, y: position.startsWith("top") ? 1 : -1 };
    for (const edge of this.widget.shadowRoot.querySelectorAll(".edge")) this.dragged(edge, toward, apply, keep);
    this.widget.$(".grip").addEventListener("dblclick", () => {
      apply(null);
      keep(null);
    });
  }

  /** The maximize button and the grip, in the widget's words. */
  label() {
    const words = this.widget.words;
    const maximize = this.widget.$(".maximize");
    const maxed = this.panel.classList.contains("maxed");
    maximize.innerHTML = maxed ? ICONS.shrink : ICONS.expand;
    maximize.title = maximize.ariaLabel = maxed ? words.restore : words.maximize;
    this.widget.$(".grip").title = words.resize;
  }

  /** One edge dragged: the width, the height or both, as its axis says; the size it is left at is kept. */
  dragged(edge, toward, apply, keep) {
    const panel = this.panel;
    const axis = edge.dataset.axis ?? "xy";
    edge.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const box = panel.getBoundingClientRect();
      const from = { x: event.clientX, y: event.clientY, width: box.width, height: box.height };
      const offset = Number.parseFloat(getComputedStyle(panel).getPropertyValue("--_offset")) || 20;
      const room = { width: window.innerWidth - 2 * offset, height: window.innerHeight - 2 * offset - 64 };
      edge.setPointerCapture(event.pointerId);
      panel.classList.add("sizing");
      edge.classList.add("held");
      // The size kept is the one last applied: the panel's box may still be moving when the pointer lets go.
      let last = null;
      const move = (at) => {
        const width = axis.includes("x") ? from.width + toward.x * (at.clientX - from.x) : from.width;
        const height = axis.includes("y") ? from.height + toward.y * (at.clientY - from.y) : from.height;
        last = {
          width: Math.round(Math.min(Math.max(width, PANEL_AT_LEAST.width), room.width)),
          height: Math.round(Math.min(Math.max(height, PANEL_AT_LEAST.height), room.height)),
        };
        apply(last);
      };
      const done = () => {
        edge.removeEventListener("pointermove", move);
        edge.removeEventListener("pointerup", done);
        edge.removeEventListener("pointercancel", done);
        panel.classList.remove("sizing");
        edge.classList.remove("held");
        if (last) keep(last);
      };
      edge.addEventListener("pointermove", move);
      edge.addEventListener("pointerup", done);
      edge.addEventListener("pointercancel", done);
    });
  }

  /** On a phone the panel is the visible part of the screen: the keyboard shrinks it and it follows. */
  fit(on) {
    const screen = window.visualViewport;
    const panel = this.panel;
    if (!screen) return;
    if (on && !this.fitting) {
      this.fitting = () => {
        panel.style.setProperty("--_vv-h", `${Math.round(screen.height)}px`);
        panel.style.setProperty("--_vv-top", `${Math.round(screen.offsetTop)}px`);
        const lines = this.widget.$(".lines");
        if (lines) lines.scrollTop = lines.scrollHeight;
      };
      screen.addEventListener("resize", this.fitting);
      screen.addEventListener("scroll", this.fitting);
      this.fitting();
    } else if (!on && this.fitting) {
      screen.removeEventListener("resize", this.fitting);
      screen.removeEventListener("scroll", this.fitting);
      panel.style.removeProperty("--_vv-h");
      panel.style.removeProperty("--_vv-top");
      this.fitting = null;
    }
  }

  /** While the panel covers the page (a phone, or maximized) the page under it holds still. */
  hold() {
    const panel = this.panel;
    const phone = matchMedia(PHONE).matches;
    const covers = !panel.hidden && (phone || panel.classList.contains("maxed"));
    this.widget.$(".scrim").hidden = !covers;
    this.fit(!panel.hidden && phone);
    if (covers && this.heldAt === undefined) {
      this.heldAt = window.scrollY;
      this.bodyWas = document.body.getAttribute("style");
      Object.assign(document.body.style, { position: "fixed", top: `-${this.heldAt}px`, left: "0", right: "0", width: "100%", overflow: "hidden" });
    } else if (!covers && this.heldAt !== undefined) {
      this.release();
    }
  }

  /** The page back where it was. */
  release() {
    if (this.heldAt === undefined) return;
    if (this.bodyWas === null) document.body.removeAttribute("style");
    else document.body.setAttribute("style", this.bodyWas);
    window.scrollTo(0, this.heldAt);
    this.heldAt = undefined;
  }

  // ── the theme ──────────────────────────────────────────────────────────────────

  /** The theme follows the visitor's machine; unless the page forced one, the header switches it, and the choice is kept. */
  theming() {
    const widget = this.widget;
    const button = widget.$(".theme");
    if (this.forced()) return;
    const chosen = read(this.themeKey);
    if (chosen === "light" || chosen === "dark") widget.setAttribute("data-theme", chosen);
    this.themeLabel();
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => this.themeLabel());
    button.addEventListener("click", () => {
      const next = this.dark() ? "light" : "dark";
      widget.setAttribute("data-theme", next);
      write(this.themeKey, next);
      this.themeLabel();
    });
  }

  forced() {
    return ["light", "dark"].includes(this.widget.getAttribute("theme"));
  }

  dark() {
    const widget = this.widget;
    if (this.forced()) return widget.getAttribute("theme") === "dark";
    const chosen = widget.getAttribute("data-theme");
    return chosen ? chosen === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  }

  /** The switch shows the theme it goes to. */
  themeLabel() {
    if (this.forced()) return;
    const button = this.widget.$(".theme");
    const words = this.widget.words;
    button.innerHTML = this.dark() ? ICONS.sun : ICONS.moon;
    button.title = button.ariaLabel = this.dark() ? words.toLight : words.toDark;
  }
}
