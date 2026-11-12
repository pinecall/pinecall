// What <pinecall-widget> draws from words it did not write: the agent's lines as the little Markdown a
// model writes, the agent's HTML kept to what is safe, the icons, and when a conversation happened.

import { fill } from "./texts.js";

// The HTML an agent may draw, and the attributes it may keep; everything else is dropped, never run.
const UI_TAGS = new Set(["p", "b", "strong", "i", "em", "u", "br", "ul", "ol", "li", "a", "code", "pre", "h3", "h4", "span", "div", "small",
  "table", "thead", "tbody", "tr", "td", "th", "img", "hr", "blockquote"]);
const UI_ATTRIBUTES = { a: ["href", "title"], img: ["src", "alt", "width", "height"], td: ["colspan"], th: ["colspan"] };
const NEVER_KEPT = new Set(["script", "style", "iframe", "object", "embed", "template", "svg", "math"]);

export const ICONS = {
  chat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 5h16v11H8l-4 4z"/></svg>`,
  phone: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/></svg>`,
  hang: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 13c5-5 13-5 18 0l-2.5 2.5L15 14v-2.5a9 9 0 0 0-6 0V14l-3.5 1.5z"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 12 20 4l-4 16-4-7z"/></svg>`,
  stop: `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2.5"/></svg>`,
  mic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>`,
  zoom: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4M11 8.5v5M8.5 11h5"/></svg>`,
  fresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/></svg>`,
  expand: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>`,
  shrink: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7"/></svg>`,
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="m15 6-6 6 6 6"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>`,
  sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="4"/><path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/></svg>`,
};

/**
 * The agent's words as the chat shows them: the little Markdown a model writes (**bold**, *italics*,
 * lists, [links](https://…)) made into elements, and nothing else. The text is escaped first, so a
 * line never becomes markup it did not say.
 */
export function said(text) {
  const escaped = text.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const inline = (line) =>
    line
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
      .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>');
  let html = "";
  let list = false;
  for (const line of escaped.split("\n")) {
    const item = /^\s*(?:[-•*]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      if (!list) html += "<ul>";
      list = true;
      html += `<li>${inline(item[1])}</li>`;
      continue;
    }
    if (list) html += "</ul>";
    list = false;
    if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  if (list) html += "</ul>";
  const out = safeHtml(html);
  out.className = "said";
  return out;
}

/**
 * The agent's HTML kept to what UI_TAGS and UI_ATTRIBUTES allow: built anew node by node, so nothing
 * runs. A link of the page's own site opens in this tab (the widget hands it to the page first); any
 * other must be https and opens in a new one.
 */
export function safeHtml(html) {
  const parsed = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html").body.firstChild;
  const copy = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return null;
    const tag = node.tagName.toLowerCase();
    if (!UI_TAGS.has(tag)) {
      // An element not allowed keeps its text, never itself: a <script>'s text is dropped with it.
      if (NEVER_KEPT.has(tag)) return null;
      const kept = document.createDocumentFragment();
      for (const child of node.childNodes) {
        const made = copy(child);
        if (made) kept.append(made);
      }
      return kept;
    }
    const made = document.createElement(tag);
    for (const name of UI_ATTRIBUTES[tag] ?? []) {
      const value = node.getAttribute(name);
      if (value === null) continue;
      if ((name === "href" || name === "src") && !/^https:\/\//i.test(value.trim())) continue;
      made.setAttribute(name, value);
    }
    if (tag === "img" && !made.hasAttribute("src")) return null;
    if (tag === "a" && !made.getAttribute("href")?.startsWith(location.origin)) {
      made.target = "_blank";
      made.rel = "noopener noreferrer";
    }
    for (const child of node.childNodes) {
      const kid = copy(child);
      if (kid) made.append(kid);
    }
    return made;
  };
  const out = document.createElement("div");
  out.className = "html";
  for (const child of parsed?.childNodes ?? []) {
    const made = copy(child);
    if (made) out.append(made);
  }
  return out;
}

/** When a kept conversation happened, as a person says it, in the widget's words: just now, 12 min ago, Tue, 3 Oct. */
export function when(at, words) {
  const ago = (Date.now() - at) / 1000;
  if (ago < 90) return words.justNow;
  if (ago < 3600) return fill(words.minAgo, { n: Math.round(ago / 60) });
  if (ago < 86400) return fill(words.hAgo, { n: Math.round(ago / 3600) });
  const day = new Date(at);
  if (ago < 6 * 86400) return day.toLocaleDateString(undefined, { weekday: "short" });
  return day.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
