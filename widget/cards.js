// What the agent draws in <pinecall-widget>'s conversation with call.send("pinecall.ui", …): choices
// to tap, a card of HTML, a row of products dealt one by one with the photo large over the chat, and
// a form it can fill as the visitor speaks. And the short line over the conversation that goes by itself.

import { ICONS, safeHtml } from "./markup.js";
import { fill } from "./texts.js";

const text = (value) => (typeof value === "string" ? value : "");
const https = (value) => /^https:\/\//i.test(value);

/** The line a `pinecall.ui` message draws, or null when it draws nothing this widget knows. */
export function card(widget, data) {
  const item = document.createElement("li");
  item.className = "agent card";
  if (data.type === "choices" && Array.isArray(data.options)) {
    if (text(data.text)) {
      const line = document.createElement("p");
      line.textContent = data.text;
      item.append(line);
    }
    item.append(choices(widget, data.options));
  } else if (data.type === "html" && typeof data.html === "string") {
    item.append(safeHtml(data.html));
  } else if (data.type === "form" && Array.isArray(data.fields) && typeof data.event === "string") {
    item.className = "agent form";
    item.append(form(widget, data));
  } else if (data.type === "products" && Array.isArray(data.items)) {
    const cards = data.items.slice(0, 6).map((one) => product(widget, one));
    if (!cards.length) return null;
    item.classList.add("products");
    const row = document.createElement("div");
    row.className = "shelf";
    // Born hidden, so no frame shows them before they are dealt.
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) for (const one of cards) one.classList.add("dealing");
    row.append(...cards);
    item.append(row);
    if (!widget.$(".lines .hint")) {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = widget.words.tapHint;
      item.append(hint);
    }
  } else {
    return null;
  }
  return item;
}

/** Buttons whose tap is the visitor's next line: the option's value, else its label. */
function choices(widget, options) {
  const row = document.createElement("div");
  row.className = "choices";
  for (const option of options.slice(0, 24)) {
    const label = typeof option === "string" ? option : String(option?.label ?? "");
    if (!label) continue;
    const value = typeof option === "object" && typeof option?.value === "string" ? option.value : label;
    const choice = document.createElement("button");
    choice.type = "button";
    choice.className = "choice";
    choice.textContent = label;
    choice.addEventListener("click", () => {
      for (const other of row.querySelectorAll("button")) other.disabled = true;
      choice.classList.add("chosen");
      void widget.choose(value);
    });
    row.append(choice);
  }
  return row;
}

/**
 * A form the agent asked for: text fields and choices whose options can show more fields (`needs`,
 * for the fields whose `shownFor` names that choice); two fields in a row with `half` sit side by
 * side. Sent, it is the event the agent named, with what she typed; she can correct it and send it
 * again. The agent can fill it as she says it (`form-fill`).
 */
function form(widget, data) {
  const words = widget.words;
  const form = document.createElement("form");
  form.className = "kf";
  form.noValidate = true;
  if (text(data.title)) {
    const title = document.createElement("p");
    title.className = "kf-title";
    title.textContent = data.title;
    form.append(title);
  }
  const inputs = new Map();
  // By choice name: its radio group, whether it must be picked, and the fields each option shows.
  const choices = new Map();
  // The pairs of half fields, each hidden when both its fields are.
  const pairs = [];
  for (const field of data.fields.slice(0, 12)) {
    const name = text(field?.name);
    if (!name) continue;
    if (field.type === "choice" && Array.isArray(field.options)) {
      const wrap = document.createElement("div");
      wrap.className = "kf-field";
      const legend = document.createElement("span");
      legend.className = "kf-label";
      legend.textContent = text(field.label);
      const group = document.createElement("div");
      group.className = "kf-opts";
      group.setAttribute("role", "radiogroup");
      const needs = new Map();
      for (const option of field.options.slice(0, 6)) {
        const row = document.createElement("label");
        row.className = "kf-opt";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = name;
        radio.value = text(option.value);
        radio.checked = radio.value === text(field.value);
        const dot = document.createElement("span");
        dot.className = "kf-dot";
        const optionName = document.createElement("span");
        optionName.className = "kf-opt-name";
        optionName.textContent = text(option.label);
        const cost = document.createElement("span");
        cost.className = "kf-opt-cost";
        cost.textContent = text(option.detail);
        row.append(radio, dot, optionName, cost);
        group.append(row);
        needs.set(radio.value, Array.isArray(option.needs) ? option.needs : []);
        radio.addEventListener("change", () => {
          group.classList.remove("kf-missing");
          show();
        });
      }
      wrap.append(legend, group);
      form.append(wrap);
      choices.set(name, { group, needs, required: Boolean(field.required) });
      continue;
    }
    const wrap = document.createElement("label");
    wrap.className = "kf-field";
    const label = document.createElement("span");
    label.className = "kf-label";
    label.textContent = text(field.label);
    const input = document.createElement("input");
    input.className = "kf-input";
    input.type = ["tel", "email"].includes(field.type) ? field.type : "text";
    input.name = name;
    input.value = text(field.value);
    input.autocomplete = text(field.autocomplete) || "on";
    if (input.type === "tel") input.inputMode = "tel";
    if (input.type === "email") input.inputMode = "email";
    input.addEventListener("input", () => input.classList.remove("kf-missing"));
    wrap.append(label, input);
    const open = pairs.at(-1);
    if (field.half && open && open === form.lastElementChild && open.childElementCount < 2) open.append(wrap);
    else if (field.half) {
      const pair = document.createElement("div");
      pair.className = "kf-pair";
      pair.append(wrap);
      form.append(pair);
      pairs.push(pair);
    } else form.append(wrap);
    inputs.set(name, { input, wrap, required: Boolean(field.required), dependent: Boolean(field.shownFor), shownFor: text(field.shownFor) });
  }
  // A field that hangs on a choice shows only when the option picked there needs it.
  const picked = (name) => choices.get(name)?.group.querySelector('input[type="radio"]:checked')?.value ?? "";
  const show = () => {
    for (const [name, { wrap, dependent, shownFor }] of inputs) {
      if (dependent) wrap.hidden = !(choices.get(shownFor)?.needs.get(picked(shownFor)) ?? []).includes(name);
    }
    for (const pair of pairs) pair.hidden = [...pair.children].every((child) => child.hidden);
  };
  show();
  if (text(data.note)) {
    const note = document.createElement("p");
    note.className = "kf-note";
    note.textContent = data.note;
    form.append(note);
  }
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "kf-send";
  submit.textContent = text(data.submit) || words.send;
  form.append(submit);
  // What she says out loud lands in the fields, lit for a moment, for her to check.
  const fillIn = (values) => {
    if (!values || typeof values !== "object") return;
    for (const [name, value] of Object.entries(values)) {
      if (typeof value !== "string" || !value) continue;
      const choice = choices.get(name);
      if (choice) {
        const radio = [...choice.group.querySelectorAll("input")].find((one) => one.value === value);
        if (radio) {
          radio.checked = true;
          choice.group.classList.remove("kf-missing");
        }
        continue;
      }
      const one = inputs.get(name);
      if (!one) continue;
      one.input.value = value;
      one.input.classList.remove("kf-missing");
      one.input.classList.add("kf-heard");
      setTimeout(() => one.input.classList.remove("kf-heard"), 1600);
    }
    show();
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    let first = null;
    const values = {};
    for (const [name, { input, wrap, required, dependent }] of inputs) {
      if (wrap.hidden) continue;
      const value = input.value.trim();
      const wrong = ((required || dependent) && !value) || (input.type === "email" && value && !/^\S+@\S+\.\S+$/.test(value));
      input.classList.toggle("kf-missing", Boolean(wrong));
      if (wrong && !first) first = input;
      values[name] = value;
    }
    for (const [name, choice] of choices) {
      values[name] = picked(name);
      const missing = choice.required && !values[name];
      choice.group.classList.toggle("kf-missing", missing);
      if (missing && !first) first = choice.group.querySelector("input");
    }
    if (first) {
      first.focus({ preventScroll: false });
      toast(widget, words.required, true);
      return;
    }
    if (!widget.publish(data.event, values)) {
      toast(widget, words.failed, true);
      return;
    }
    widget.lowerKeyboard();
    document.activeElement?.blur?.();
    submit.textContent = words.formSent;
    submit.disabled = true;
    setTimeout(() => {
      submit.disabled = false;
      submit.textContent = words.formUpdate;
    }, 2500);
  });
  if (text(data.id)) widget.forms.set(data.id, fillIn);
  return form;
}

/**
 * One product card: the photo, the name and colour, the price and the sizes left; a tap opens it. An
 * item with no `sizes` at all is a product without sizes; an empty list is one sold out.
 */
function product(widget, one) {
  const words = widget.words;
  const card = document.createElement("button");
  card.type = "button";
  card.className = "product";
  const image = text(one.image);
  if (https(image)) {
    const frame = document.createElement("span");
    frame.className = "frame";
    const img = document.createElement("img");
    img.src = image;
    img.alt = `${text(one.name)} ${text(one.color)}`;
    img.loading = "lazy";
    const zoom = document.createElement("i");
    zoom.className = "zoom";
    zoom.innerHTML = ICONS.zoom;
    frame.append(img, zoom);
    card.append(frame);
  }
  const name = document.createElement("b");
  name.textContent = [text(one.name), text(one.color)].filter(Boolean).join(" · ");
  const price = document.createElement("span");
  price.textContent = text(one.price);
  card.append(name, price);
  const sized = Array.isArray(one.sizes);
  const left = sized ? one.sizes.filter((size) => typeof size === "string") : [];
  if (sized) {
    const sizes = document.createElement("small");
    sizes.textContent = left.length ? fill(words.sizes, { sizes: left.join(" · ") }) : words.soldOut;
    card.append(sizes);
  }
  const large = text(one.large);
  const big = https(large) ? large : image;
  if (https(big)) {
    const shown = { name: text(one.name), color: text(one.color), title: name.textContent, price: price.textContent, sized, sizes: left };
    card.addEventListener("click", () => viewer(widget, big, shown));
  } else card.disabled = true;
  return card;
}

/**
 * The photo large over the chat, the chat still there under it: its sizes to pick and the "add to
 * cart" button, which tells the agent (`cart.add`) and closes. A tap outside, × or Escape closes.
 */
function viewer(widget, src, product) {
  const words = widget.words;
  widget.$(".viewer")?.remove();
  const viewer = document.createElement("div");
  viewer.className = "viewer";
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-label", product.title);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "viewer-close";
  close.ariaLabel = words.close;
  close.textContent = "×";
  const img = document.createElement("img");
  img.src = src;
  img.alt = product.title;
  const sheet = document.createElement("div");
  sheet.className = "viewer-sheet";
  const caption = document.createElement("p");
  const name = document.createElement("b");
  name.textContent = product.title;
  caption.append(name, document.createTextNode(` · ${product.price}`));
  sheet.append(caption);
  const shut = () => {
    viewer.classList.remove("on");
    widget.removeEventListener("keydown", onKey);
    setTimeout(() => viewer.remove(), 180);
  };
  const onKey = (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      shut();
    }
  };
  const add = (size) => {
    const sent = widget.publish("cart.add", { name: product.name, color: product.color, ...(size ? { size } : {}) });
    const what = [words.added, product.title, size].filter(Boolean).join(" · ");
    toast(widget, sent ? what : words.notAdded, !sent);
    if (sent) shut();
  };
  if (!product.sized || product.sizes.length) {
    let chosen = product.sizes.length === 1 ? product.sizes[0] : null;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "viewer-add";
    const label = () => {
      const ready = !product.sized || chosen;
      button.textContent = !product.sized ? words.addToCart : chosen ? `${words.addToCart} · ${chosen}` : words.pickSize;
      button.disabled = !ready;
    };
    if (product.sized) {
      const sizes = document.createElement("div");
      sizes.className = "viewer-sizes";
      sizes.setAttribute("role", "radiogroup");
      sizes.setAttribute("aria-label", words.pickSize);
      for (const size of product.sizes) {
        const pick = document.createElement("button");
        pick.type = "button";
        pick.textContent = size;
        pick.setAttribute("role", "radio");
        pick.setAttribute("aria-checked", String(size === chosen));
        pick.addEventListener("click", () => {
          chosen = size;
          for (const other of sizes.children) other.setAttribute("aria-checked", String(other === pick));
          label();
        });
        sizes.append(pick);
      }
      sheet.append(sizes);
    }
    label();
    button.addEventListener("click", () => {
      if (product.sized && !chosen) return;
      add(chosen);
    });
    sheet.append(button);
  } else {
    const out = document.createElement("p");
    out.className = "viewer-out";
    out.textContent = words.soldOut;
    sheet.append(out);
  }
  viewer.append(close, img, sheet);
  // Only the backdrop and × close it: the sizes and the button are hers to tap.
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer || event.target === img) shut();
  });
  close.addEventListener("click", shut);
  widget.addEventListener("keydown", onKey);
  widget.lowerKeyboard();
  widget.$(".panel").append(viewer);
  requestAnimationFrame(() => viewer.classList.add("on"));
  close.focus({ preventScroll: true });
}

/** A shelf's cards come in one by one, the row sliding along to the newest. */
export function deal(item) {
  const shelf = item.querySelector(".shelf");
  if (!shelf) return;
  const cards = [...shelf.children].filter((one) => one.classList.contains("dealing"));
  if (!cards.length) return;
  // No snapping while the cards come in: the row stays put, and only slides, by what is missing,
  // when a card lands partly out of view.
  shelf.classList.add("dealing");
  shelf.scrollLeft = 0;
  cards.forEach((one, at) => {
    setTimeout(() => {
      one.classList.remove("dealing");
      const missing = one.offsetLeft + one.offsetWidth - (shelf.scrollLeft + shelf.clientWidth);
      if (missing > 0) shelf.scrollBy({ left: missing + 8, behavior: "smooth" });
      if (at === cards.length - 1) setTimeout(() => shelf.classList.remove("dealing"), 600);
    }, 320 + at * 640);
  });
}

/** A short line over the conversation that goes by itself. */
export function toast(widget, words, failed = false) {
  widget.$(".toast")?.remove();
  const line = document.createElement("div");
  line.className = `toast${failed ? " failed" : ""}`;
  line.setAttribute("role", "status");
  line.textContent = words;
  widget.$(".panel").append(line);
  requestAnimationFrame(() => line.classList.add("on"));
  setTimeout(() => {
    line.classList.remove("on");
    setTimeout(() => line.remove(), 250);
  }, 2600);
}
