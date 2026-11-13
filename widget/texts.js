// Every word <pinecall-widget> says, by language, and how a site says any of them its own way.
//
// `lang` on the tag picks the table (`en` unless it names another one here). Over it, a site sets
// any key with a `text-<key>` attribute (`addToCart` is `text-add-to-cart`) or with the `texts`
// property, `{ addToCart: "Add to bag" }`, which wins over both. `{name}` and `{company}` are the
// tag's own; the other placeholders (`{n}`, `{left}`…) are filled where the text is shown.

const EN = {
  assistant: "Assistant",
  open: "Talk to {name}",
  close: "Close",
  write: "Write to {name}…",
  send: "Send",
  call: "Call {name}",
  hangUpToChat: "Hang up and carry on in chat",
  fresh: "New conversation",
  more: "More",
  maximize: "Maximize",
  restore: "Restore size",
  resize: "Drag to resize, double-click to reset",
  toLight: "Light theme",
  toDark: "Dark theme",
  typing: "{name} is typing…",
  connecting: "Connecting…",
  reconnecting: "Reconnecting…",
  live: "Online",
  listening: "{name} is listening",
  ended: "Conversation ended.",
  tapToHear: "Tap to hear {name}",
  micRefused: "We couldn't use the microphone: let's carry on in chat.",
  failed: "We couldn't connect. Try again in a moment.",
  formSent: "Done, we have it",
  formUpdate: "Update my details",
  required: "Fill this in",
  dictate: "Dictate a message",
  stopDictating: "Stop dictating",
  hearing: "Listening…",
  dictationFailed: "I couldn't hear you, try again",
  addToCart: "Add to cart",
  pickSize: "Pick your size",
  sizes: "Sizes {sizes}",
  added: "Added to cart",
  notAdded: "I couldn't add it, try again",
  tapHint: "Tap a photo to see it or add it",
  soldOut: "Sold out",
  history: "Your conversations",
  clear: "Clear",
  backToChat: "Back to the conversation",
  carryOn: "Carry on this conversation",
  forget: "Delete this conversation",
  aCall: "A call",
  aChat: "A chat",
  callWord: "Call",
  chatWord: "Chat",
  endedWord: "ended",
  justNow: "just now",
  minAgo: "{n} min ago",
  hAgo: "{n} h ago",
  talkHere: "Talk in your browser",
  talkHereSub: "Speak with {name} now, no phone needed",
  callUs: "Call us",
  callUsSub: "From your phone",
  callUsByCode: "From your phone, and follow the call here",
  callName: "Call {name}",
  dial: "Call",
  keyCode: "Key this code on your phone",
  anyTime: "any time during the call",
  theCode: "the code: {digits}",
  showsHere: "Your conversation shows up here, live, the moment the code is keyed.",
  waiting: "Waiting for your call…",
  expiresIn: "expires in {left}",
  codeExpired: "The code expired.",
  newCode: "Get a new code",
  gettingCode: "Getting your code…",
  onTheLine: "Live: {name} is on the line.",
  callTheNumber: "Call the number and {name} picks up.",
  yourCall: "☎ your call",
  callFrom: "☎ a call from {who}",
  endedWhy: "— ended: {why}",
  showTools: "Show tools",
  hangUp: "Hang up",
  captions: "Captions",
  walks: "Walks",
  stop: "Stop",
  pause: "Pause",
  back: "Back",
  next: "Next",
  more: "More walks",
  ask: "Ask me to show you…",
  askAgent: "Ask the agent",
  looking: "Looking…",
  notHere: "I can't find that on this page.",
  forAgent: "That one is a question for the agent.",
};

const ES = {
  assistant: "Asistente",
  open: "Hablá con {name}",
  close: "Cerrar",
  write: "Escribile a {name}…",
  send: "Enviar",
  call: "Llamar a {name}",
  hangUpToChat: "Colgar y seguir por chat",
  fresh: "Nueva conversación",
  more: "Más",
  maximize: "Agrandar",
  restore: "Volver al tamaño",
  resize: "Arrastrá para cambiar el tamaño; doble clic para volver",
  toLight: "Tema claro",
  toDark: "Tema oscuro",
  typing: "{name} está escribiendo…",
  connecting: "Conectando…",
  reconnecting: "Reconectando…",
  live: "En línea",
  listening: "{name} te escucha",
  ended: "Conversación terminada.",
  tapToHear: "Tocá para oír a {name}",
  micRefused: "No pudimos usar el micrófono: seguimos por chat.",
  failed: "No pudimos conectar. Probá de nuevo en un momento.",
  formSent: "Listo, ya lo vemos",
  formUpdate: "Actualizar mis datos",
  required: "Completá este dato",
  dictate: "Dictar un mensaje",
  stopDictating: "Terminar de dictar",
  hearing: "Te escucho…",
  dictationFailed: "No pude escucharte, probá de nuevo",
  addToCart: "Agregar al carrito",
  pickSize: "Elegí tu talle",
  sizes: "Talles {sizes}",
  added: "Agregado al carrito",
  notAdded: "No pude agregarlo, probá de nuevo",
  tapHint: "Tocá una foto para verla o agregarla",
  soldOut: "Agotado",
  history: "Tus conversaciones",
  clear: "Borrar",
  backToChat: "Volver a la conversación",
  carryOn: "Seguir esta conversación",
  forget: "Eliminar esta conversación",
  aCall: "Una llamada",
  aChat: "Un chat",
  callWord: "Llamada",
  chatWord: "Chat",
  endedWord: "terminada",
  justNow: "recién",
  minAgo: "hace {n} min",
  hAgo: "hace {n} h",
  talkHere: "Hablá desde el navegador",
  talkHereSub: "Hablá con {name} ahora, sin teléfono",
  callUs: "Llamanos",
  callUsSub: "Desde tu teléfono",
  callUsByCode: "Desde tu teléfono, y seguí la llamada acá",
  callName: "Llamá a {name}",
  dial: "Llamar",
  keyCode: "Marcá este código en tu teléfono",
  anyTime: "en cualquier momento de la llamada",
  theCode: "el código: {digits}",
  showsHere: "Tu conversación aparece acá, en vivo, en cuanto marques el código.",
  waiting: "Esperando tu llamada…",
  expiresIn: "vence en {left}",
  codeExpired: "El código venció.",
  newCode: "Pedir un código nuevo",
  gettingCode: "Pidiendo tu código…",
  onTheLine: "En vivo: {name} está en la línea.",
  callTheNumber: "Llamá al número y {name} te atiende.",
  yourCall: "☎ tu llamada",
  callFrom: "☎ una llamada de {who}",
  endedWhy: "— terminó: {why}",
  showTools: "Ver herramientas",
  hangUp: "Colgar",
  captions: "Subtítulos",
  walks: "Recorridos",
  stop: "Detener",
  pause: "Pausar",
  back: "Anterior",
  next: "Siguiente",
  more: "Más recorridos",
  ask: "Pedime que te muestre…",
  askAgent: "Preguntale al agente",
  looking: "Buscando…",
  notHere: "No encuentro eso en esta página.",
  forAgent: "Esa pregunta es para el agente.",
};

export const TEXTS = { en: EN, es: ES };

/** The language of the tag's own words: `lang`'s first part when there is a table for it, else English. */
export function languageOf(element) {
  const lang = (element.getAttribute("lang") ?? "en").toLowerCase().split("-")[0];
  return lang in TEXTS ? lang : "en";
}

/** `{key}` in a text filled from `params`; a placeholder with nothing to fill it stays as written. */
/**
 * What a server said went wrong, when it said it in words, else `otherwise`. A gateway refuses a body
 * it cannot read with a list in `detail`: written out as it came, that list read "[object Object]".
 */
export function refusalOf(answered, otherwise) {
  const detail = answered?.detail;
  return typeof detail === "string" && detail.trim() !== "" ? detail : otherwise;
}

export function fill(text, params = {}) {
  return text.replace(/\{(\w+)\}/g, (whole, key) => (key in params ? String(params[key]) : whole));
}

/** The attribute that sets one key: `addToCart` is `text-add-to-cart`. */
function attributeOf(key) {
  return `text-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

/**
 * The words of one widget: its language's table, each key replaced by the tag's `text-<key>`
 * attribute when it has one and by `overrides` (the `texts` property) over that, with `{name}` and
 * `{company}` filled in. A key no table has is not a text of the widget, and is left out.
 */
export function wordsOf(element, lang, overrides, own) {
  const words = {};
  for (const [key, text] of Object.entries(TEXTS[lang])) {
    const chosen = overrides?.[key] ?? element.getAttribute(attributeOf(key)) ?? text;
    words[key] = fill(String(chosen), own);
  }
  return words;
}
