// <pinecall-widget>: a floating button that connects a visitor to a Pinecall agent by phone,
// browser voice call, or chat.
//
// The page's own server mints visit tokens and relays the call log with the org's API key, so
// the key never reaches the browser. The same endpoints serve every agent of the org.
//
//   <script type="module" src="/pinecall/pinecall-widget.js"></script>
//   <pinecall-widget agent="bidfire-sales" name="Sam" company="BidFire"
//                    token-url="/pinecall/token.php" log-url="/pinecall/log.php"></pinecall-widget>
//
// Attributes:
//   agent       required · the agent's slug
//   token-url   required · mints visit tokens (POST {agent, scope}). Alternatively set the
//               `tokenProvider` property to (scope, agent) => Promise<token JSON>
//   log-url     optional · lists phone calls and relays a call's log (GET ?agent=&list=1,
//               GET ?agent=&call=). Enables log-based transcripts, the live phone call under
//               "Call us" and the tools toggle; without it, text comes from LiveKit text streams
//   code-url    optional · requests a call code (POST {agent}); your server calls the gateway's
//               POST /v1/codes with the org key. Or set `codeProvider` to (agent) => Promise<code
//               JSON>. "Call us" then shows the number and a 4-digit code, and follows only the
//               call that enters it; no log-url needed
//   gateway     optional · where codes and call logs are read; defaults to this file's origin,
//               or cloud.pinecall.io when served from jsDelivr
//   phone       optional · number for "Call us" without a code; with neither, "Call us" is hidden
//   name        optional · display name, "Assistant" by default
//   company     optional · shown under the name
//   tagline     optional · line under the name, e.g. "books your technician"
//   label       optional · button text, "Talk to <name>" by default
//   lang        optional · the language of the widget's own words: en (default) or es
//   icon        optional · "none" leaves the button without its icon
//   button      optional · "none" draws no button at all: open the panel with toggle() from your own
//   (your own button) a child with slot="button" takes the default button's place and opens the panel;
//               it is your element, styled by your page's CSS like any other
//   greeting    optional · plain-text first message, shown before any call starts
//   autostart   optional · open straight into a voice call; the microphone is requested in the
//               same click that opens the panel
//   position    optional · bottom-right (default), bottom-left, top-right, top-left, or inline
//               (rendered where the tag is, in the page flow)
//   theme       optional · auto (default: follows the browser, and the visitor may switch it from the
//               panel's header, their choice kept in this browser), light, or dark (forced: no switch)
//   history     optional · "off" keeps no conversations in this browser; by default the visitor's
//               last 20 chats and calls are kept in localStorage, listed in the menu, and any one
//               of them can be read again
//   look        optional · "dot": the button is a face that speaks with the agent's voice, and a
//               click is a voice call with no panel (pinecall-dot.js, on @pinecall/room). The log is
//               read from `gateway` with the call's own token; --pc-dot-size sizes it (64px)
//   tutor       optional · with look="dot": the dot walks the page with a pointer of its own, for an
//               agent that extends @pinecall/dot/agent's Tutor
//
// Styling: the font is inherited. These custom properties apply in both themes: --pc-accent,
// --pc-accent-soft, --pc-ink, --pc-muted, --pc-line, --pc-radius, --pc-offset, --pc-font,
// --pc-font-size, --pc-z, and for the button alone --pc-button-bg, --pc-button-ink,
// --pc-button-border, --pc-button-radius, --pc-button-padding, --pc-button-shadow,
// --pc-button-weight, --pc-button-font-size. Parts: `button`, `button-icon`, `button-label` and
// `panel`, e.g. pinecall-widget::part(button) — anything CSS can say, the page may say there.
//
// The panel is the visitor's to size: drag the corner away from the button, or maximize it from the
// header; the size they leave is kept in this browser. `--pc-panel-width` / `--pc-panel-height` set
// the size a panel opens at, and an element's own `part="panel"` still takes any CSS the page says.
//
// The agent can put things on the visitor's screen with call.send("pinecall.ui", data), drawn in the
// conversation: {type: "choices", text?, options: [{label, value?}]} as buttons whose tap is the
// visitor's next line (value, else label), and {type: "html", html} as a card. The HTML is kept to
// text, lists, tables, links (https, new tab), images (https) and code; scripts and styles never run.
//
// Events on the tag: pinecall:open, pinecall:started {call, scope}, pinecall:ended {call}, and with
// look="dot" pinecall:ui {detail: what the agent sent on pinecall.ui}, which a dot cannot draw.
//
// The page tells the agent what the visitor does with `event(name, data)` on the tag: the agent's
// onEvent(name, data) runs when its class accepts that name from a participant.
//
// Uses LiveKit's client SDK from a CDN; no build step.

import { ParticipantKind, Room, RoomEvent, Track } from "https://cdn.jsdelivr.net/npm/livekit-client@2/+esm";

const TRANSCRIPTION = "lk.transcription";
const CHAT = "lk.chat";
// Said before leaving on a hang-up: the call ends at once instead of waiting for the visitor.
const HANGUP = "pinecall.hangup";
// A fact about the page, for the agent's onEvent: {name, data}.
const EVENT = "pinecall.event";
// What the agent puts on the visitor's screen (call.send("pinecall.ui", …)): choices to tap, or HTML.
const UI = "pinecall.ui";
// The HTML an agent may draw, and the attributes it may keep; everything else is dropped, never run.
const UI_TAGS = new Set(["p", "b", "strong", "i", "em", "u", "br", "ul", "ol", "li", "a", "code", "pre", "h3", "h4", "span", "div", "small",
  "table", "thead", "tbody", "tr", "td", "th", "img", "hr", "blockquote"]);
const UI_ATTRIBUTES = { a: ["href", "title"], img: ["src", "alt", "width", "height"], td: ["colspan"], th: ["colspan"] };
const SEGMENT_ID = "lk.segment_id";
const TRANSCRIPTION_FINAL = "lk.transcription_final";
const TOOLS_SETTING = "pinecall-widget:show-tools";
const SIZE_SETTING = "pinecall-widget:panel-size";
// How many kept conversations the menu shows before "See all".
const RECENT_IN_VIEW = 3;
const THEME_SETTING = "pinecall-widget:theme";
// The smallest a visitor can drag the panel to, in px.
const PANEL_AT_LEAST = { width: 320, height: 380 };
// The visitor's own conversations, kept in this browser alone: the newest first, a few lines each.
const KEPT = "pinecall-widget:conversations";
const KEPT_AT_MOST = 20;
const LINES_AT_MOST = 200;
// Default gateway: the origin that served this file, or Pinecall's when served from the CDN.
const SERVED_FROM = new URL(import.meta.url).origin;
const A_GATEWAY = SERVED_FROM.includes("jsdelivr.net") ? "https://cloud.pinecall.io" : SERVED_FROM;

// Every word the widget says, by language: `lang="es"` on the tag picks Spanish, anything else English.
const WORDS = {
  en: {
    assistant: "Assistant",
    talkTo: (name) => `Talk to ${name}`,
    close: "Close",
    micRefused: (why) => `The microphone was not allowed (${why}): chat instead, or allow it and try again.`,
    callUs: "Call us",
    callUsByCode: "From your phone, and follow the call here",
    talk: "Talk in your browser",
    talkSub: (name) => `Speak with ${name} now, no phone needed`,
    chat: "Chat",
    chatSub: (name) => `Type, and ${name} answers`,
    yours: "Your conversations",
    clear: "Clear",
    answersNow: (name) => `${name} answers right away`,
    aCall: "A call",
    aChat: "A chat",
    call: "Call",
    dial: "Call",
    expiresIn: (left) => `expires in ${left}`,
    yourCall: "☎ your call",
    callFrom: (who) => `☎ a call from ${who}`,
    endedWhy: (why) => `— ended: ${why}`,
    lines: (n) => `${n} line${n === 1 ? "" : "s"}`,
    ended: "ended",
    back: "Back",
    showTools: "Show tools",
    newCall: "New call",
    newChat: "New chat",
    continueCall: "Continue the call",
    callShort: "Call",
    talkShort: "Talk",
    chatShort: "Write",
    recent: "Recent",
    seeAll: (n) => `See all (${n})`,
    seeFewer: "See fewer",
    deleteChat: "Delete conversation",
    maximize: "Maximize",
    restore: "Restore size",
    resize: "Drag to resize, double-click to reset",
    toLight: "Switch to the light theme",
    toDark: "Switch to the dark theme",
    writeOn: "Write to carry on…",
    gettingCode: "Getting your code…",
    callName: (name) => `Call ${name}`,
    keyCode: "Key this code on your phone",
    anyTime: "any time during the call",
    theCode: (digits) => `the code: ${digits}`,
    showsHere: "Your conversation shows up here, live, the moment the code is keyed.",
    waiting: "Waiting for your call",
    waitingDots: "Waiting for your call…",
    codeExpired: "The code expired.",
    onTheLine: (name) => `Live: ${name} is on the line.`,
    newCode: "Get a new code",
    callTheNumber: (name) => `Call the number and ${name} picks up.`,
    connecting: "Connecting…",
    writeTo: (name) => `Write to ${name}…`,
    send: "Send",
    hangUp: "Hang up",
    captions: "Captions",
    walks: "Walks",
    stop: "Stop",
    pause: "Pause",
    more: "More walks",
    endChat: "End chat",
    endedDot: "Ended.",
    tapToHear: "Tap to hear the agent",
    listening: (name) => `Live. ${name} is listening.`,
    live: "Live.",
    hangingUp: "Hanging up…",
    justNow: "just now",
    minAgo: (n) => `${n} min ago`,
    hAgo: (n) => `${n} h ago`,
  },
  es: {
    assistant: "Asistente",
    talkTo: (name) => `Habla con ${name}`,
    close: "Cerrar",
    micRefused: (why) => `No se permitió el micrófono (${why}): escribe en el chat, o permítelo y vuelve a intentarlo.`,
    callUs: "Llámanos",
    callUsByCode: "Desde tu teléfono, y sigue la llamada aquí",
    talk: "Habla desde el navegador",
    talkSub: (name) => `Habla con ${name} ahora, sin teléfono`,
    chat: "Chat",
    chatSub: (name) => `Escribe, y ${name} te responde`,
    yours: "Tus conversaciones",
    clear: "Borrar",
    answersNow: (name) => `${name} responde al momento`,
    aCall: "Una llamada",
    aChat: "Un chat",
    call: "Llamada",
    dial: "Llamar",
    expiresIn: (left) => `caduca en ${left}`,
    yourCall: "☎ tu llamada",
    callFrom: (who) => `☎ una llamada de ${who}`,
    endedWhy: (why) => `— terminó: ${why}`,
    lines: (n) => `${n} ${n === 1 ? "línea" : "líneas"}`,
    ended: "terminada",
    back: "Volver",
    showTools: "Ver herramientas",
    newCall: "Nueva llamada",
    newChat: "Nuevo chat",
    continueCall: "Seguir la llamada",
    callShort: "Llamar",
    talkShort: "Hablar",
    chatShort: "Escribir",
    recent: "Recientes",
    seeAll: (n) => `Ver todas (${n})`,
    seeFewer: "Ver menos",
    deleteChat: "Eliminar conversación",
    maximize: "Maximizar",
    restore: "Restaurar tamaño",
    resize: "Arrastra para cambiar el tamaño; doble clic para restablecerlo",
    toLight: "Cambiar al tema claro",
    toDark: "Cambiar al tema oscuro",
    writeOn: "Escribe para seguir…",
    gettingCode: "Pidiendo tu código…",
    callName: (name) => `Llama a ${name}`,
    keyCode: "Marca este código en tu teléfono",
    anyTime: "en cualquier momento de la llamada",
    theCode: (digits) => `el código: ${digits}`,
    showsHere: "Tu conversación aparece aquí, en directo, en cuanto marques el código.",
    waiting: "Esperando tu llamada",
    waitingDots: "Esperando tu llamada…",
    codeExpired: "El código caducó.",
    onTheLine: (name) => `En directo: ${name} está en la línea.`,
    newCode: "Pedir un código nuevo",
    callTheNumber: (name) => `Llama al número y ${name} contesta.`,
    connecting: "Conectando…",
    writeTo: (name) => `Escribe a ${name}…`,
    send: "Enviar",
    hangUp: "Colgar",
    captions: "Subtítulos",
    walks: "Recorridos",
    stop: "Detener",
    pause: "Pausar",
    more: "Más recorridos",
    endChat: "Terminar el chat",
    endedDot: "Terminada.",
    tapToHear: "Toca para oír al agente",
    listening: (name) => `En directo. ${name} te escucha.`,
    live: "En directo.",
    hangingUp: "Colgando…",
    justNow: "ahora mismo",
    minAgo: (n) => `hace ${n} min`,
    hAgo: (n) => `hace ${n} h`,
  },
};
// Must match the entry types a log-url relay requests.
const LOG_TYPES = "call.started,user.transcript,agent.transcript,turn.user,turn.agent,tool.call,tool.result,call.ended";

/** Format a NANP number as +1 XXX XXX XXXX; other numbers are returned unchanged. */
function spaced(number) {
  const nanp = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(number);
  return nanp ? `+1 ${nanp[1]} ${nanp[2]} ${nanp[3]}` : number;
}

// Dark palette for `theme="dark"` and for `auto` under prefers-color-scheme: dark. Page-set custom
// properties still take precedence.
const DARK = `
    color-scheme: dark;
    color: var(--pc-ink, #e5e7eb);
    --_soft: var(--pc-accent-soft, color-mix(in srgb, var(--_accent) 22%, #17181c));
    --_accent-ink: color-mix(in srgb, var(--_accent) 55%, #fff);
    --_line: var(--pc-line, #2c2f36);
    --_muted: var(--pc-muted, #9ca3af);
    --_surface: #17181c;
    --_raised: #24262c;
    --_field: #3a3d45;
    --_live: #4ade80;
    --_failed: #f87171;
    --_danger-line: #7f1d1d;
    --_shadow: rgba(0, 0, 0, .5);
`;

const STYLE = `
  :host {
    all: initial;
    display: contents;
    color-scheme: light;
    font-family: var(--pc-font, inherit);
    font-size: var(--pc-font-size, 15px);
    line-height: 1.45;
    color: var(--pc-ink, #1f2937);
    --_accent: var(--pc-accent, #6d28d9);
    --_accent-ink: var(--_accent);
    --_soft: var(--pc-accent-soft, #f5f3ff);
    --_line: var(--pc-line, #e8e9ee);
    --_muted: var(--pc-muted, #6b7280);
    --_surface: #fff;
    --_raised: #f4f5f8;
    --_field: #d9dbe3;
    --_live: #16a34a;
    --_failed: #dc2626;
    --_danger-line: #fecaca;
    --_shadow: rgba(17, 24, 39, .16);
    --_radius: var(--pc-radius, 18px);
    --_offset: var(--pc-offset, 20px);
    --_z: var(--pc-z, 2147483000);
  }
  :host([theme="dark"]), :host([data-theme="dark"]) { ${DARK} }
  @media (prefers-color-scheme: dark) { :host(:not([theme="light"]):not([data-theme="light"])) { ${DARK} } }
  :host([position="inline"]) { display: inline-block; }
  * { box-sizing: border-box; }
  button { font: inherit; }
  .fab { position: fixed; right: var(--_offset); bottom: var(--_offset); z-index: var(--_z); display: inline-flex; align-items: center; gap: 9px;
         padding: var(--pc-button-padding, 12px 18px 12px 14px); border: var(--pc-button-border, 0); border-radius: var(--pc-button-radius, 999px);
         cursor: pointer; color: var(--pc-button-ink, #fff); font-weight: var(--pc-button-weight, 500); font-size: var(--pc-button-font-size, inherit);
         letter-spacing: .01em; background: var(--pc-button-bg, var(--_accent));
         box-shadow: var(--pc-button-shadow, 0 10px 28px var(--_shadow), 0 1px 2px rgba(0,0,0,.08)); transition: transform .15s ease, box-shadow .15s ease; }
  .fab:hover { transform: translateY(-2px); }
  .fab:active { transform: translateY(0); }
  .fab .icon { display: inline-flex; }
  .fab svg { width: 20px; height: 20px; }
  .fab[hidden], :host([icon="none"]) .fab .icon { display: none; }
  .panel { position: fixed; right: var(--_offset); bottom: calc(var(--_offset) + 64px); z-index: var(--_z); width: min(392px, calc(100vw - 2 * var(--_offset)));
           height: auto; max-height: min(660px, calc(100vh - 110px)); display: flex; flex-direction: column; background: var(--_surface); color: inherit;
           border-radius: var(--_radius); overflow: hidden; box-shadow: 0 24px 64px var(--_shadow), 0 0 0 1px var(--_line); transform-origin: bottom right;
           animation: pc-in .18s cubic-bezier(.2,.8,.2,1); }
  .panel.wide { width: min(var(--pc-panel-width, 480px), calc(100vw - 2 * var(--_offset))); height: min(var(--pc-panel-height, 760px), calc(100vh - 110px)); }
  /* What the visitor dragged it to. */
  .panel.sized { width: min(var(--_w), calc(100vw - 2 * var(--_offset))); height: min(var(--_h), calc(100vh - 2 * var(--_offset) - 64px)); max-height: none; }
  /* Maximized: the whole window but the page's own margin, whatever corner it opens from. */
  .panel.maxed { inset: 0 !important; width: auto !important; height: auto !important; max-height: none !important; border-radius: 0; box-shadow: none; }
  /* The panel is sized from the edges that face the page: the side for its width, the top (or the
     bottom, when it opens from the top) for its height, the corner for both. Nothing is drawn until
     a pointer is over one: then a thin line in the accent says which edge it holds. */
  .edge { position: absolute; z-index: 3; touch-action: none; }
  .edge::after { content: ""; position: absolute; background: var(--_accent); opacity: 0; transition: opacity .12s; border-radius: 2px; }
  .edge:hover::after, .panel.sizing .edge.held::after { opacity: .7; }
  .edge-x { top: 14px; bottom: 14px; left: 0; width: 7px; cursor: ew-resize; }
  .edge-x::after { top: 0; bottom: 0; left: 0; width: 2px; }
  .edge-y { left: 14px; right: 14px; top: 0; height: 7px; cursor: ns-resize; }
  .edge-y::after { left: 0; right: 0; top: 0; height: 2px; }
  .grip { top: 0; left: 0; width: 14px; height: 14px; cursor: nwse-resize; }
  .grip::after { top: 0; left: 0; width: 10px; height: 10px; background: none; border-top: 2px solid var(--_accent); border-left: 2px solid var(--_accent); border-top-left-radius: var(--_radius); }
  :host([position="bottom-left"]) .edge-x, :host([position="top-left"]) .edge-x { left: auto; right: 0; }
  :host([position="bottom-left"]) .edge-x::after, :host([position="top-left"]) .edge-x::after { left: auto; right: 0; }
  :host([position="top-right"]) .edge-y, :host([position="top-left"]) .edge-y { top: auto; bottom: 0; }
  :host([position="top-right"]) .edge-y::after, :host([position="top-left"]) .edge-y::after { top: auto; bottom: 0; }
  :host([position="bottom-left"]) .grip { left: auto; right: 0; cursor: nesw-resize; }
  :host([position="bottom-left"]) .grip::after { left: auto; right: 0; border-left: 0; border-right: 2px solid var(--_accent); border-top-left-radius: 0; border-top-right-radius: var(--_radius); }
  :host([position="top-right"]) .grip { top: auto; bottom: 0; cursor: nesw-resize; }
  :host([position="top-right"]) .grip::after { top: auto; bottom: 0; border-top: 0; border-bottom: 2px solid var(--_accent); border-top-left-radius: 0; border-bottom-left-radius: var(--_radius); }
  :host([position="top-left"]) .grip { top: auto; bottom: 0; left: auto; right: 0; cursor: nwse-resize; }
  :host([position="top-left"]) .grip::after { top: auto; bottom: 0; left: auto; right: 0; border-top: 0; border-left: 0; border-bottom: 2px solid var(--_accent); border-right: 2px solid var(--_accent); border-top-left-radius: 0; border-bottom-right-radius: var(--_radius); }
  .panel.sizing { transition: none; user-select: none; animation: none; }
  .panel.maxed .edge, :host([position="inline"]) .edge { display: none; }
  .panel[hidden] { display: none; }
  /* Under a panel that covers the page, the page is gone: nothing of it shows, not even where iOS
     slides the screen for its keyboard. */
  .scrim { position: fixed; left: 0; right: 0; top: -100vh; height: 300vh; z-index: calc(var(--_z) - 1); background: var(--_surface); }
  .scrim[hidden] { display: none; }
  header .head-back { display: none; }
  .carry-row { justify-content: center; }
  @keyframes pc-in { from { opacity: 0; transform: translateY(8px) scale(.98); } to { opacity: 1; transform: none; } }
  :host([position="bottom-left"]) .fab, :host([position="bottom-left"]) .panel { right: auto; left: var(--_offset); }
  :host([position="bottom-left"]) .panel { transform-origin: bottom left; }
  :host([position="top-right"]) .fab { bottom: auto; top: var(--_offset); }
  :host([position="top-right"]) .panel { bottom: auto; top: calc(var(--_offset) + 64px); transform-origin: top right; }
  :host([position="top-left"]) .fab { right: auto; bottom: auto; left: var(--_offset); top: var(--_offset); }
  :host([position="top-left"]) .panel { right: auto; bottom: auto; left: var(--_offset); top: calc(var(--_offset) + 64px); transform-origin: top left; }
  :host([position="inline"]) .fab { position: static; }
  @media (max-width: 520px) {
    /* The visible part of the screen, not the screen: iOS slides a keyboard over the page without
       making it shorter, and a panel as tall as the screen would push its head and its lines off
       the top. The two variables are the visual viewport's, kept by fitToTheScreen(). */
    .panel, .panel.wide, .panel.sized, .panel.maxed { top: var(--_vv-top, 0px) !important; left: 0 !important; right: 0 !important; bottom: auto !important;
      width: auto !important; height: 100vh !important; height: var(--_vv-h, 100dvh) !important; max-height: none !important; border-radius: 0; }
    .edge, header .maximize, .panel .sidebar { display: none !important; }
    /* Inside a conversation on a phone the foot's buttons give their room to the lines: back is an
       arrow in the head, the X ends the conversation, and a new one starts from the menu. */
    .panel.wide footer { display: none; }
    .panel.wide header .head-back { display: grid; margin-left: -6px; }
    .panel.wide header { padding: 10px 12px; gap: 4px; }
    .panel.maxed.wide { display: flex !important; }
    .panel.maxed.wide header { justify-content: flex-start; }
    .panel.maxed.wide header .avatar { display: grid !important; }
    .panel.maxed.wide header .who { display: block !important; }
  }
  @media (prefers-reduced-motion: reduce) { .panel { animation: none; } .fab { transition: none; } }
  header { display: flex; align-items: center; gap: 12px; padding: 14px 14px 14px 18px; flex: 0 0 auto; border-bottom: 1px solid var(--_line); }
  header .avatar { position: relative; width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; display: grid; place-items: center;
                   background: var(--_soft); color: var(--_accent-ink); font-weight: 500; font-size: 16px; }
  header .avatar::after { content: ""; position: absolute; right: -1px; bottom: -1px; width: 11px; height: 11px; border-radius: 50%;
                          background: var(--_live); border: 2px solid var(--_surface); }
  header .who { flex: 1 1 auto; min-width: 0; }
  header h2 { margin: 0; font-size: 15.5px; font-weight: 500; line-height: 1.25; }
  header p { margin: 2px 0 0; font-size: 12.5px; color: var(--_muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  header .close, header .tool { width: 34px; height: 34px; border: 0; border-radius: 50%; background: transparent; color: var(--_muted); font-size: 22px; cursor: pointer;
                  line-height: 1; display: grid; place-items: center; flex: 0 0 auto; }
  header .tool { width: 32px; height: 32px; }
  header .tool svg { width: 17px; height: 17px; }
  header .close:hover, header .tool:hover { background: var(--_raised); color: inherit; }
  header { gap: 6px; } header .avatar { margin-right: 6px; }
  /* A theme the page forced is not the visitor's to change. */
  :host([theme="light"]) header .theme, :host([theme="dark"]) header .theme, :host([position="inline"]) header .maximize { display: none; }
  .body { overscroll-behavior: contain; padding: 14px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; flex: 1 1 auto; min-height: 0; }
  .option { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 12px 12px 12px; text-align: left; cursor: pointer;
            border: 1px solid var(--_line); border-radius: 14px; background: var(--_surface); color: inherit; text-decoration: none;
            transition: border-color .12s, background .12s, transform .12s; }
  .option:hover { border-color: color-mix(in srgb, var(--_accent) 45%, var(--_line)); background: var(--_soft); transform: translateY(-1px); }
  .option .icon { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: var(--_soft); color: var(--_accent-ink); flex: 0 0 40px; }
  .option:hover .icon { background: var(--_accent); color: #fff; }
  .option .icon svg { width: 19px; height: 19px; }
  .option .words { flex: 1 1 auto; min-width: 0; }
  .option b { display: block; font-weight: 500; font-size: 14.5px; }
  .option span { display: block; font-size: 12.5px; color: var(--_muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .option .chev { color: var(--_muted); flex: 0 0 auto; }
  .option .chev svg { width: 16px; height: 16px; }
  .kept-head { display: flex; align-items: baseline; justify-content: space-between; margin: 6px 2px 0; font-size: 12px; font-weight: 500; color: var(--_muted);
               text-transform: uppercase; letter-spacing: .06em; }
  .kept-head button { border: 0; background: transparent; color: var(--_muted); font-size: 12px; cursor: pointer; text-transform: none; letter-spacing: 0; padding: 0; }
  .kept-head button:hover { color: var(--_failed); }
  .kept { padding: 10px 12px; border-radius: 12px; }
  .kept .icon { width: 34px; height: 34px; border-radius: 10px; flex-basis: 34px; }
  .kept .icon svg { width: 16px; height: 16px; }
  .kept b { font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kept span { font-size: 12px; }
  .number { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-radius: 14px; background: var(--_soft); }
  .number b { font-size: 20px; font-weight: 500; letter-spacing: .01em; }
  .number a { font: inherit; font-weight: 500; padding: 9px 14px; border-radius: 999px; background: var(--_accent); color: #fff; text-decoration: none; }
  .dial { display: flex; flex-direction: column; gap: 14px; flex: 0 0 auto; }
  .step { display: grid; grid-template-columns: 26px 1fr; gap: 4px 12px; align-items: start; }
  .step .n { grid-row: span 2; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: 13px; font-weight: 500;
             background: var(--_soft); color: var(--_accent-ink); }
  .step .say { font-size: 14px; font-weight: 500; line-height: 26px; }
  .step .say small { font-weight: 400; color: var(--_muted); font-size: 13px; }
  .step .number { padding: 10px 10px 10px 14px; }
  .number a { display: inline-flex; align-items: center; gap: 6px; }
  .number a svg { width: 15px; height: 15px; }
  .digits { display: flex; gap: 8px; }
  .digits span { width: 52px; height: 60px; display: grid; place-items: center; font-size: 30px; font-weight: 500; font-variant-numeric: tabular-nums;
                 border: 1.5px solid color-mix(in srgb, var(--_accent) 30%, var(--_line)); border-radius: 14px; background: var(--_surface); }
  .waiting { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 2px; }
  .waiting .status { display: inline-flex; align-items: center; gap: 8px; }
  .waiting .status:not(.failed)::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--_accent); animation: pc-pulse 1.4s ease-in-out infinite; }
  .expires { font-size: 12px; color: var(--_muted); padding: 3px 9px; border-radius: 999px; background: var(--_raised); font-variant-numeric: tabular-nums; }
  .soon { display: grid; place-items: center; text-align: center; padding: 18px; font-size: 13px; color: var(--_muted);
          border: 1.5px dashed var(--_line); border-radius: 14px; flex: 1 1 auto; min-height: 110px; }
  @keyframes pc-pulse { 0%, 100% { opacity: .35; transform: scale(.85); } 50% { opacity: 1; transform: scale(1); } }
  @media (prefers-reduced-motion: reduce) { .waiting .status::before { animation: none; } }
  .lines { overscroll-behavior: contain; list-style: none; margin: 0; padding: 2px 0; display: flex; flex-direction: column; gap: 8px; flex: 1 1 auto; overflow-y: auto; min-height: 120px; }
  .lines li { padding: 9px 13px; border-radius: 16px; max-width: 84%; font-size: 14px; line-height: 1.45; overflow-wrap: anywhere; }
  .lines li.agent { background: var(--_soft); align-self: flex-start; border-bottom-left-radius: 5px; }
  .lines li.user { background: var(--_accent); color: #fff; align-self: flex-end; border-bottom-right-radius: 5px; }
  .lines li.interim { opacity: .6; }
  .lines li.mark { background: none; color: var(--_muted); font: 12px/1.4 ui-monospace, Menlo, monospace; max-width: 100%; padding: 2px 8px; }
  .lines li.mark[hidden] { display: none; }
  .lines li.card { max-width: 100%; }
  .lines li.card p { margin: 0 0 10px; }
  .choices { display: flex; flex-wrap: wrap; gap: 8px; }
  .choice { font: inherit; font-size: 13.5px; padding: 7px 13px; border-radius: 999px; border: 1px solid var(--_line); background: var(--_surface); color: inherit; cursor: pointer;
            transition: border-color .12s, background .12s; }
  .choice:hover:not([disabled]) { border-color: var(--_accent); background: var(--_soft); }
  .choice[disabled] { cursor: default; opacity: .45; }
  .choice.chosen { opacity: 1; border-color: var(--_accent); background: var(--_accent); color: #fff; }
  .html { display: flex; flex-direction: column; gap: 8px; overflow-wrap: anywhere; }
  .html > * { margin: 0; }
  .html a { color: var(--_accent-ink); }
  .html img { max-width: 100%; height: auto; border-radius: 10px; }
  .html pre { padding: 10px 12px; border-radius: 10px; background: var(--_raised); overflow-x: auto; font: 12.5px/1.5 ui-monospace, Menlo, monospace; }
  .html table { border-collapse: collapse; font-size: 13px; }
  .html td, .html th { padding: 4px 8px; border-bottom: 1px solid var(--_line); text-align: left; }
  .status { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--_muted); }
  .status.live { color: var(--_live); }
  .status.live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--_live); box-shadow: 0 0 0 3px color-mix(in srgb, var(--_live) 25%, transparent); }
  .status.failed { color: var(--_failed); }
  .row { display: flex; gap: 8px; flex: 0 0 auto; align-items: center; }
  input[type=text] { flex: 1; font: inherit; font-size: max(16px, 1em); padding: 11px 16px; border: 1px solid var(--_field); border-radius: 999px; outline: none; color: inherit; background: var(--_surface); min-width: 0; }
  input[type=text]:focus { border-color: var(--_accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--_accent) 20%, transparent); }
  .btn { font: inherit; font-weight: 500; padding: 9px 14px; border: 0; border-radius: 999px; cursor: pointer; background: var(--_accent); color: #fff; }
  .btn.send { width: 42px; height: 42px; padding: 0; display: grid; place-items: center; flex: 0 0 42px; }
  .btn.send svg { width: 18px; height: 18px; }
  .btn.quiet { background: var(--_raised); color: inherit; }
  .btn.danger { background: var(--_surface); color: var(--_failed); border: 1px solid var(--_danger-line); }
  .btn[disabled] { opacity: .5; cursor: default; }
  footer { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 10px 16px; border-top: 1px solid var(--_line); flex: 0 0 auto; min-height: 50px; }
  footer .right { display: flex; align-items: center; gap: 10px; }
  footer .status { padding: 2px 0; }
  .back { display: inline-flex; align-items: center; gap: 4px; border: 0; background: transparent; color: var(--_accent-ink); font-weight: 500; cursor: pointer; padding: 6px 8px 6px 4px; border-radius: 999px; }
  .back:hover { background: var(--_soft); }
  .back svg { width: 16px; height: 16px; }
  .toggle { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--_muted); cursor: pointer; user-select: none; }
  .toggle input { accent-color: var(--_accent); }
  /* The welcome is for the maximized panel; the small one opens on its choices alone. */
  .panel:not(.maxed) .greeting { display: none; }
  .greeting { margin: 0; padding: 10px 14px; border-radius: 16px; border-bottom-left-radius: 5px; align-self: flex-start;
              max-width: 84%; font-size: 14px; background: var(--_soft); white-space: pre-line; }
  .kept-when { font-size: 12.5px; color: var(--_muted); }

  .sidebar { display: none; }
  /* Maximized and inside a conversation: the conversations at the side, the way a chat app has them. */
  .panel.maxed.wide { display: grid; grid-template-columns: 276px minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
  .panel.maxed.wide header { grid-column: 2; grid-row: 1; justify-content: flex-end; }
  .panel.maxed.wide header .avatar, .panel.maxed.wide header .who { display: none; }
  .panel.maxed.wide .body { grid-column: 2; grid-row: 2; }
  /* The X ends the conversation and the list holds the others, so the foot has nothing left to say. */
  .panel.maxed.wide footer { display: none; }
  .panel.maxed.wide .sidebar { grid-column: 1; grid-row: 1 / 3; display: flex; flex-direction: column; gap: 4px; padding: 14px 10px; overflow-y: auto;
                               background: var(--_raised); border-right: 1px solid var(--_line); }
  .side-brand { display: flex; align-items: center; gap: 10px; padding: 4px 8px 12px; }
  .side-brand .avatar { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--_soft); color: var(--_accent-ink); font-weight: 500; font-size: 13px; }
  .side-brand b { font-size: 16px; font-weight: 500; letter-spacing: -.01em; }
  .side-new { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 10px; border: 0; border-radius: 10px; background: transparent; color: inherit; cursor: pointer; font-size: 14.5px; text-align: left; }
  .side-new:hover { background: color-mix(in srgb, var(--_muted) 16%, transparent); }
  .side-new svg { width: 18px; height: 18px; color: var(--_muted); }
  .side-head { margin: 18px 10px 4px; font-size: 12px; font-weight: 500; color: var(--_muted); }
  .side-list { display: flex; flex-direction: column; gap: 1px; }
  .side-item { display: flex; align-items: center; gap: 2px; border-radius: 10px; }
  .side-item:hover { background: color-mix(in srgb, var(--_muted) 14%, transparent); }
  .side-open { flex: 1 1 auto; min-width: 0; padding: 8px 10px; border: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; }
  .side-open b { display: block; font-size: 14px; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .side-open span { display: block; font-size: 11.5px; color: var(--_muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .side-del { flex: 0 0 auto; width: 30px; height: 30px; margin-right: 4px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent;
              color: var(--_muted); cursor: pointer; opacity: 0; transition: opacity .12s; }
  .side-del svg { width: 16px; height: 16px; }
  .side-item:hover .side-del, .side-del:focus-visible { opacity: 1; }
  .side-del:hover { color: var(--_failed); background: color-mix(in srgb, var(--_failed) 12%, transparent); }
  .side-item.on { background: color-mix(in srgb, var(--_muted) 22%, transparent); }
  .side-item.on .side-del { opacity: .7; }
  .options { display: flex; flex-direction: column; gap: 10px; }
  .actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .actions.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .action { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 14px 8px 12px; border: 1px solid var(--_line); border-radius: 16px;
            background: var(--_surface); color: inherit; font-size: 13.5px; cursor: pointer; transition: border-color .12s, background .12s, transform .12s; }
  .action:hover { border-color: color-mix(in srgb, var(--_accent) 45%, var(--_line)); background: var(--_soft); transform: translateY(-1px); }
  .action-icon { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--_accent); color: #fff; }
  .action-icon svg { width: 19px; height: 19px; }
  .kept-head { margin-top: 10px; }
  .recent { display: flex; flex-direction: column; }
  .recent-row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 8px; border: 0; border-radius: 10px; background: transparent; color: inherit;
                text-align: left; cursor: pointer; font-size: 13.5px; }
  .recent-row[hidden] { display: none; }
  .recent-row:hover { background: var(--_raised); }
  .recent-icon { flex: 0 0 auto; display: grid; place-items: center; color: var(--_muted); }
  .recent-icon svg { width: 15px; height: 15px; }
  .recent-text { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .recent-when { flex: 0 0 auto; font-size: 12px; color: var(--_muted); }
  .recent-more { align-self: flex-start; margin: 2px 0 0 8px; padding: 4px 0; border: 0; background: transparent; color: var(--_accent-ink); font-size: 13px; cursor: pointer; }

  /* Maximized: the whole window, read like a chat app — one centred column, the welcome as a
     headline, the ways in side by side, the conversation without boxes, the composer at the foot. */
  .panel.maxed header { border-bottom-color: transparent; padding: 14px 20px; }
  .panel.maxed .body { padding: 0 24px 24px; gap: 14px; align-items: center; }
  .panel.maxed .body > * { width: 100%; max-width: 760px; }
  .panel.maxed footer { border-top-color: transparent; justify-content: center; }
  .panel.maxed footer > .status:only-child { font-size: 12px; }
  .panel.maxed .greeting { align-self: center; margin: max(48px, 12vh) 0 18px; padding: 0; background: none; border-radius: 0; text-align: center;
                           font-size: clamp(24px, 3.2vw, 34px); font-weight: 500; line-height: 1.25; letter-spacing: -.02em;
                           background-image: linear-gradient(90deg, var(--_accent-ink), color-mix(in srgb, var(--_accent-ink) 55%, #22d3ee));
                           -webkit-background-clip: text; background-clip: text; color: transparent; }
  .panel.maxed .options { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .panel.maxed .actions { gap: 12px; }
  .panel.maxed .action { padding: 22px 12px 18px; gap: 12px; font-size: 15px; border-radius: 18px; background: var(--_raised); border-color: transparent; }
  .panel.maxed .action:hover { background: var(--_soft); }
  .panel.maxed .action-icon { width: 48px; height: 48px; }
  .panel.maxed .recent-row { padding: 11px 10px; font-size: 14.5px; }
  .panel.maxed .option { flex-direction: column; align-items: flex-start; gap: 14px; padding: 18px; border-radius: 18px; min-height: 132px; background: var(--_raised); border-color: transparent; }
  .panel.maxed .option:hover { background: var(--_soft); border-color: transparent; }
  .panel.maxed .option .words span { white-space: normal; }
  .panel.maxed .option .chev { display: none; }
  .panel.maxed .kept-head { margin-top: 18px; }
  .panel.maxed .kept { background: transparent; border-color: transparent; }
  .panel.maxed .kept:hover { background: var(--_raised); }
  .panel.maxed .lines { padding: 24px 0 8px; gap: 22px; }
  .panel.maxed .lines li { font-size: 15.5px; line-height: 1.6; }
  .panel.maxed .lines li.agent { background: none; padding: 0; max-width: 100%; border-radius: 0; }
  .panel.maxed .lines li.user { background: var(--_raised); color: inherit; border-radius: 20px; padding: 10px 16px; max-width: 72%; }
  .panel.maxed .row { margin: 4px 0 6px; padding: 6px 6px 6px 18px; border: 1px solid var(--_line); border-radius: 28px; background: var(--_surface);
                      box-shadow: 0 6px 24px color-mix(in srgb, var(--_shadow) 50%, transparent); }
  .panel.maxed .row input[type=text] { border: 0; box-shadow: none; padding: 10px 0; background: transparent; }
  .panel.maxed .row input[type=text]:focus { box-shadow: none; }
  .panel.maxed .row .btn.send { width: 40px; height: 40px; flex-basis: 40px; }
`;

const ICONS = {
  spark: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1M5.6 18.4l2.1-2.1m8.6-8.6 2.1-2.1"/><circle cx="12" cy="12" r="3"/></svg>`,
  phone: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/></svg>`,
  mic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>`,
  chat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h16v11H8l-4 4z"/></svg>`,
  chevron: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 6 6 6-6 6"/></svg>`,
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 6-6 6 6 6"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12 20 4l-4 16-4-7z"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>`,
  expand: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>`,
  shrink: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7"/></svg>`,
  sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/></svg>`,
};

/** An agent's HTML kept to what UI_TAGS and UI_ATTRIBUTES allow: built anew node by node, so nothing runs. */
function safeHtml(html) {
  const parsed = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html").body.firstChild;
  const copy = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return null;
    const tag = node.tagName.toLowerCase();
    if (!UI_TAGS.has(tag)) {
      // An element not allowed keeps its text, never itself: a <script>'s text is dropped with it.
      if (["script", "style", "iframe", "object", "embed", "template", "svg", "math"].includes(tag)) return null;
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
    if (tag === "a") {
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
function when(at, w) {
  const ago = (Date.now() - at) / 1000;
  if (ago < 90) return w.justNow;
  if (ago < 3600) return w.minAgo(Math.round(ago / 60));
  if (ago < 86400) return w.hAgo(Math.round(ago / 3600));
  const day = new Date(at);
  if (ago < 6 * 86400) return day.toLocaleDateString(undefined, { weekday: "short" });
  return day.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * Renders one call's log as a transcript: caller turns, agent turns and tool calls in log order.
 * The tools toggle shows or hides tool entries without redrawing.
 */
class Transcript {
  constructor(list, showTools, words = WORDS.en) {
    this.words = words;
    this.list = list;
    this.showTools = showTools;
    this.stream = null;
    this.lines = new Map();
    this.hearing = null;
    this.seen = 0;
    this.onAgent = null;
    this.onEnd = null;
    // Told every line as it settles, by key, so the widget keeps the conversation.
    this.onLine = null;
    // What was said before this call, in the calls it carries on: drawn above its own log.
    this.earlier = [];
  }

  follow(url, attempt = 0) {
    this.stop();
    if (attempt === 0) {
      this.list.replaceChildren();
      this.lines.clear();
      this.hearing = null;
      this.seen = 0;
      for (const one of this.earlier) this.line(one.who === "user" ? "user" : "agent", one.text);
    }
    const stream = new EventSource(url);
    this.stream = stream;
    // A new EventSource has no Last-Event-ID, so a reconnect replays the log from the start;
    // skip entries by seq to avoid drawing them twice.
    const on = (type, draw) =>
      stream.addEventListener(type, (event) => {
        // Not `lastEventId`: an event without an id inherits the previous one's.
        const seq = JSON.parse(event.data).seq;
        if (typeof seq === "number") {
          if (seq <= this.seen) return;
          this.seen = seq;
        }
        draw(event);
      });
    const data = (event) => JSON.parse(event.data).data ?? {};
    stream.onerror = () => {
      if (stream.readyState !== EventSource.CLOSED) return;
      stream.close();
      if (this.stream === stream && attempt < 10) setTimeout(() => this.follow(url, attempt + 1), 1000);
    };
    // Settle the line on the final transcript; `turn.user` arrives later, after end-of-utterance.
    on("user.transcript", (event) => {
      const heard = data(event);
      if (!this.hearing) this.hearing = this.line("user interim", "");
      this.hearing.textContent = heard.text ?? "";
      if (heard.final) this.hearing.className = "user";
      this.scroll();
    });
    on("turn.user", (event) => {
      const item = this.hearing ?? this.line("user", "");
      item.className = "user";
      item.textContent = data(event).text ?? "";
      this.hearing = null;
      this.onLine?.(`turn_${JSON.parse(event.data).seq}`, "user", item.textContent);
    });
    on("agent.transcript", (event) => {
      const word = data(event);
      this.spoken(`speech_${word.speech_id}`, word.text ?? "", word.start);
      this.onAgent?.();
    });
    on("turn.agent", (event) => {
      const turn = data(event);
      this.said(`speech_${turn.speech_id}`, turn.text ?? "", true);
      this.onAgent?.();
    });
    on("tool.call", (event) => {
      const tool = data(event);
      this.mark(`→ ${tool.name}(${JSON.stringify(tool.arguments ?? {})})`);
    });
    on("tool.result", (event) => {
      const result = data(event);
      this.mark(`← ${result.name}: ${result.error ?? JSON.stringify(result.output ?? "").slice(0, 120)}`);
    });
    on("call.ended", (event) => {
      this.mark(this.words.endedWhy(data(event).reason ?? ""), true);
      this.stop();
      this.onEnd?.();
    });
  }

  /** Show typed text immediately, greyed until the log's `turn.user` confirms it. */
  typed(text) {
    this.hearing = this.line("user interim", text);
  }

  /** Remove the pending typed line after a failed send. */
  untyped() {
    this.hearing?.remove();
    this.hearing = null;
  }

  stop() {
    this.stream?.close();
    this.stream = null;
    for (const item of this.lines.values()) item.pace?.timers.forEach(clearTimeout);
  }

  /**
   * Show one agent word in sync with playback. Words arrive before they play, with a start time
   * relative to the speech; that offset is counted from the first word's arrival. Untimed words
   * show immediately.
   */
  spoken(key, text, start) {
    let item = this.lines.get(key);
    if (!item) {
      item = this.line("agent interim", "");
      this.lines.set(key, item);
      item.pace = { anchor: performance.now(), last: 0, timers: [] };
    }
    const pace = item.pace;
    const show = () => {
      item.textContent += text;
      this.scroll();
    };
    const due = typeof start === "number" ? Math.max(pace.anchor + start * 1000, pace.last) : performance.now();
    pace.last = due;
    const wait = due - performance.now();
    if (wait <= 0) show();
    else pace.timers.push(setTimeout(show, wait));
  }

  /** Replace the pending words with the final text of the agent's turn. */
  said(key, text, final) {
    let item = this.lines.get(key);
    if (!item) {
      item = this.line("agent", "");
      this.lines.set(key, item);
    }
    item.pace?.timers.forEach(clearTimeout);
    item.pace = null;
    item.className = `agent${final ? "" : " interim"}`;
    item.textContent = text;
    this.scroll();
    if (final) this.onLine?.(key, "agent", text);
  }

  mark(text, always = false) {
    const item = this.line("mark", text);
    if (!always) {
      item.dataset.tool = "1";
      item.hidden = !this.showTools();
    }
  }

  line(className, text) {
    const item = document.createElement("li");
    item.className = className;
    item.textContent = text;
    this.list.append(item);
    this.scroll();
    return item;
  }

  tools(shown) {
    for (const item of this.list.querySelectorAll("li[data-tool]")) item.hidden = !shown;
  }

  scroll() {
    this.list.scrollTop = this.list.scrollHeight;
  }
}

class PinecallWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.room = null;
    this.streamLines = new Map();
    this.transcript = null;
    this.phonePoll = null;
    this.codeWait = null;
    this.codeClock = null;
    // The conversation under way, as it is being kept.
    this.current = null;
    // The call under way and a token of its own, to say its hang-up at the gateway's door.
    this.hangup = null;
  }

  // ── the visitor's conversations, kept in this browser ─────────────────────────

  keepsHistory() {
    return this.getAttribute("history") !== "off";
  }

  /** Every conversation kept for this agent, newest first. */
  kept() {
    if (!this.keepsHistory()) return [];
    try {
      const all = JSON.parse(localStorage.getItem(KEPT) ?? "[]");
      return Array.isArray(all) ? all.filter((one) => one.agent === this.agent) : [];
    } catch {
      return [];
    }
  }

  /** Write the list back, this agent's and every other's, the newest first and at most a few. */
  keep(mine) {
    if (!this.keepsHistory()) return;
    try {
      const all = JSON.parse(localStorage.getItem(KEPT) ?? "[]");
      const others = Array.isArray(all) ? all.filter((one) => one.agent !== this.agent) : [];
      localStorage.setItem(KEPT, JSON.stringify([...mine.slice(0, KEPT_AT_MOST), ...others]));
    } catch {
      // storage unavailable; nothing is kept
    }
    this.renderSide();
  }

  /**
   * Maximized and inside a conversation, the conversations kept are a list at the side, the way a
   * chat app has them: New chat on top, every other one under it, the one in view marked.
   */
  renderSide() {
    const side = this.$(".sidebar");
    if (!side) return;
    const w = this.words;
    const kept = this.kept();
    const open = this.current?.call ?? this.viewing ?? "";
    side.innerHTML = `<div class="side-brand"><span class="avatar" aria-hidden="true"></span><b></b></div>
      <button class="side-new" type="button">${ICONS.chat}<span>${w.newChat}</span></button>
      ${kept.length > 0 ? `<div class="side-head">${w.yours}</div>` : ""}
      <div class="side-list">${kept.map((one, at) => `<div class="side-item${one.call === open ? " on" : ""}" data-at="${at}"><button class="side-open" type="button"><b></b><span></span></button><button class="side-del" type="button" aria-label="${w.deleteChat}" title="${w.deleteChat}">${ICONS.trash}</button></div>`).join("")}</div>`;
    side.querySelector(".side-brand .avatar").textContent = (this.name.trim()[0] ?? "A").toUpperCase();
    side.querySelector(".side-brand b").textContent = this.name;
    side.querySelector(".side-new").addEventListener("click", async () => {
      await this.leave();
      this.conversation("chat");
    });
    for (const row of side.querySelectorAll(".side-item")) {
      const one = kept[Number(row.dataset.at)];
      const first = one.lines.find((line) => line.who === "user") ?? one.lines[0];
      row.querySelector("b").textContent = first?.text ?? (one.scope === "talk" ? w.aCall : w.aChat);
      row.querySelector(".side-open span").textContent = `${one.scope === "talk" ? w.call : w.chat} · ${when(one.started_at, w)}`;
      row.querySelector(".side-open").addEventListener("click", async () => {
        if (one.call === open) return;
        await this.leave();
        this.review(one);
      });
      row.querySelector(".side-del").addEventListener("click", () => this.forget(one, open));
    }
  }

  /** Delete one kept conversation from this browser. The one in view is hung up and a new chat opens. */
  async forget(one, open) {
    if (one.call === this.current?.call) this.current = null;
    this.keep(this.kept().filter((other) => other.call !== one.call));
    if (one.call !== open) return;
    await this.hungUp();
    await this.leave();
    this.conversation("chat");
  }

  /**
   * A conversation just opened: kept from now on, as its lines settle. One resumed stays one
   * conversation: the same row, its earlier lines, the new call and the token to resume it next.
   * Back in the same call with a log-url, that call's own lines are left to its log, read again.
   */
  began(call, scope, resume = null, earlier = null) {
    const own = (one) => this.logUrl && String(one.key).startsWith(`${call}:`);
    const lines = (earlier?.lines ?? []).filter((one) => !own(one));
    const started_at = earlier?.started_at ?? Date.now();
    this.current = { call, scope, agent: this.agent, started_at, ended_at: null, lines, resume };
    const gone = new Set([call, earlier?.call]);
    this.keep([this.current, ...this.kept().filter((one) => !gone.has(one.call))]);
  }

  /** One settled line of the conversation under way; the same key again replaces it. */
  kept_line(key, who, text) {
    const current = this.current;
    if (!current || !text) return;
    // Keyed by call: a resumed conversation's calls number their lines alike.
    key = `${current.call}:${key}`;
    const at = current.lines.findIndex((one) => one.key === key);
    if (at >= 0) current.lines[at] = { key, who, text };
    else current.lines.push({ key, who, text });
    if (current.lines.length > LINES_AT_MOST) current.lines.splice(0, current.lines.length - LINES_AT_MOST);
    this.keep([current, ...this.kept().filter((one) => one.call !== current.call)]);
  }

  /** The conversation under way is over. */
  ended() {
    if (!this.current) return;
    this.current.ended_at = Date.now();
    this.keep([this.current, ...this.kept().filter((one) => one.call !== this.current.call)]);
    this.current = null;
  }

  forgetAll() {
    this.keep([]);
    this.menu();
  }

  /** The log-url with this agent's query appended. */
  log(query) {
    return `${this.logUrl}${this.logUrl.includes("?") ? "&" : "?"}agent=${encodeURIComponent(this.agent)}&${query}`;
  }

  connectedCallback() {
    this.agent = this.getAttribute("agent") ?? "";
    this.words = WORDS[(this.getAttribute("lang") ?? "en").toLowerCase().split("-")[0]] ?? WORDS.en;
    const w = this.words;
    this.name = this.getAttribute("name") ?? w.assistant;
    this.company = this.getAttribute("company") ?? "";
    this.tagline = this.getAttribute("tagline") ?? "";
    this.phone = this.getAttribute("phone") ?? "";
    this.logUrl = this.getAttribute("log-url") ?? "";
    this.codeUrl = this.getAttribute("code-url") ?? "";
    this.gateway = (this.getAttribute("gateway") ?? A_GATEWAY).replace(/\/+$/, "");
    this.greeting = this.getAttribute("greeting") ?? "";
    // Present means on, unless the value is "false".
    this.autostart = this.hasAttribute("autostart") && this.getAttribute("autostart") !== "false";
    const label = this.getAttribute("label") ?? w.talkTo(this.name);
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <slot name="button"></slot>
      <button class="fab" part="button"><span class="icon" part="button-icon">${ICONS.spark}</span><span class="label" part="button-label"></span></button>
      <div class="scrim" hidden></div>
      <section class="panel" part="panel" hidden>
        <header>
          <button class="tool head-back" type="button" aria-label="${w.back}">${ICONS.back}</button>
          <span class="avatar" aria-hidden="true"></span>
          <div class="who"><h2></h2><p></p></div>
          <button class="tool theme" type="button"></button>
          <button class="tool maximize" type="button"></button>
          <button class="close" aria-label="${w.close}">×</button>
        </header>
        <div class="body"></div>
        <footer></footer>
        <aside class="sidebar"></aside>
        <div class="edge edge-x" data-axis="x"></div>
        <div class="edge edge-y" data-axis="y"></div>
        <div class="edge grip" data-axis="xy" role="separator" aria-orientation="horizontal"></div>
      </section>`;
    // Set as text, never HTML: the name and the company come from the page's own attributes, but
    // a page that interpolates them from elsewhere must not get markup through here.
    this.shadowRoot.querySelector(".avatar").textContent = (this.name.trim()[0] ?? "A").toUpperCase();
    this.shadowRoot.querySelector("header h2").textContent = this.name;
    this.shadowRoot.querySelector("header p").textContent = [this.company, this.tagline].filter(Boolean).join(" · ");
    this.$ = (selector) => this.shadowRoot.querySelector(selector);
    this.$(".fab .label").textContent = label;
    // look="dot": the face and its call, from the module beside this file; until it has loaded, a
    // click waits for it, and a dot that cannot load leaves the plain button.
    if (this.getAttribute("look") === "dot") {
      // The plain button never shows while the dot loads: it is the dot, or, if that fails, the button.
      this.$(".fab").style.visibility = "hidden";
      this.dotting = import("./pinecall-dot.js").then(
        ({ Dot }) => (this.dot = new Dot(this)),
        (failed) => {
          console.warn("pinecall-widget: the dot could not load, so the button is the plain one", failed);
          this.$(".fab").style.visibility = "";
          return null;
        },
      );
    }
    const open = () => {
      if (this.dot) return this.dot.click();
      if (this.dotting) return this.dotting.then((dot) => (dot ? dot.click() : this.toggle()));
      return this.autostart ? this.start() : this.toggle();
    };
    this.$(".fab").addEventListener("click", open);
    // The page's own launcher, when it gives one: a child with slot="button" replaces the default
    // button, and whatever it is — a button, a link, a card — opens the panel. "button=none" draws none.
    const slot = this.$('slot[name="button"]');
    const launch = () => {
      const own = slot.assignedElements();
      this.$(".fab").hidden = own.length > 0 || this.getAttribute("button") === "none";
      for (const element of own) {
        // The mark is an empty string, which reads false: ask whether it is there, not what it says.
        if ("pinecallOpens" in element.dataset) continue;
        element.dataset.pinecallOpens = "";
        element.addEventListener("click", (event) => {
          event.preventDefault();
          open();
        });
      }
    };
    slot.addEventListener("slotchange", launch);
    launch();
    this.$(".close").addEventListener("click", () => this.hide());
    this.$(".head-back").addEventListener("click", async () => {
      await this.leave();
      this.menu();
    });
    this.sizing();
    this.theming();
    matchMedia("(max-width: 520px)").addEventListener("change", () => this.holdPage());
    this.menu();
  }

  // ── the visitor's panel: its size, and its theme ──────────────────────────────

  /** Drag the corner away from the button to size the panel; maximize it from the header. */
  sizing() {
    const panel = this.$(".panel");
    const grip = this.$(".grip");
    const maximize = this.$(".maximize");
    const w = this.words;
    grip.title = w.resize;
    const apply = (size) => {
      panel.classList.toggle("sized", Boolean(size));
      if (size) {
        panel.style.setProperty("--_w", `${size.width}px`);
        panel.style.setProperty("--_h", `${size.height}px`);
      }
    };
    const kept = () => {
      try {
        const size = JSON.parse(localStorage.getItem(SIZE_SETTING) ?? "null");
        return size && size.width >= PANEL_AT_LEAST.width && size.height >= PANEL_AT_LEAST.height ? size : null;
      } catch {
        return null;
      }
    };
    const keep = (size) => {
      try {
        if (size) localStorage.setItem(SIZE_SETTING, JSON.stringify(size));
        else localStorage.removeItem(SIZE_SETTING);
      } catch {
        // storage unavailable; the size holds for this page
      }
    };
    apply(kept());
    const show = () => {
      const maxed = panel.classList.contains("maxed");
      maximize.innerHTML = maxed ? ICONS.shrink : ICONS.expand;
      maximize.title = maximize.ariaLabel = maxed ? w.restore : w.maximize;
    };
    show();
    maximize.addEventListener("click", () => {
      panel.classList.toggle("maxed");
      show();
      this.holdPage();
    });
    this.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && panel.classList.contains("maxed")) {
        panel.classList.remove("maxed");
        show();
        this.holdPage();
      }
    });
    // The grip sits at the corner away from the button, so a drag toward the page's middle grows it.
    const position = this.getAttribute("position") ?? "bottom-right";
    const toward = { x: position.endsWith("left") ? 1 : -1, y: position.startsWith("top") ? 1 : -1 };
    for (const edge of this.shadowRoot.querySelectorAll(".edge")) this.dragged(edge, panel, toward, apply, keep);
    grip.addEventListener("dblclick", () => {
      apply(null);
      keep(null);
    });
  }

  /** One edge dragged: the width, the height or both, as its axis says, kept in the window. */
  dragged(edge, panel, toward, apply, keep) {
    const axis = edge.dataset.axis ?? "xy";
    edge.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const box = panel.getBoundingClientRect();
      const from = { x: event.clientX, y: event.clientY, width: box.width, height: box.height };
      const room = {
        width: window.innerWidth - 2 * (Number.parseFloat(getComputedStyle(panel).getPropertyValue("--_offset")) || 20),
        height: window.innerHeight - 2 * (Number.parseFloat(getComputedStyle(panel).getPropertyValue("--_offset")) || 20) - 64,
      };
      edge.setPointerCapture(event.pointerId);
      panel.classList.add("sizing");
      edge.classList.add("held");
      const move = (at) => {
        const width = axis.includes("x") ? from.width + toward.x * (at.clientX - from.x) : from.width;
        const height = axis.includes("y") ? from.height + toward.y * (at.clientY - from.y) : from.height;
        apply({
          width: Math.round(Math.min(Math.max(width, PANEL_AT_LEAST.width), room.width)),
          height: Math.round(Math.min(Math.max(height, PANEL_AT_LEAST.height), room.height)),
        });
      };
      const done = () => {
        edge.removeEventListener("pointermove", move);
        edge.removeEventListener("pointerup", done);
        edge.removeEventListener("pointercancel", done);
        panel.classList.remove("sizing");
        edge.classList.remove("held");
        const size = { width: Math.round(panel.getBoundingClientRect().width), height: Math.round(panel.getBoundingClientRect().height) };
        keep(panel.classList.contains("sized") ? size : null);
      };
      edge.addEventListener("pointermove", move);
      edge.addEventListener("pointerup", done);
      edge.addEventListener("pointercancel", done);
    });
  }

  /** The theme follows the visitor's machine; unless the page forced one, the header switches it. */
  theming() {
    const button = this.$(".theme");
    const w = this.words;
    const forced = () => ["light", "dark"].includes(this.getAttribute("theme"));
    const dark = () => (forced() ? this.getAttribute("theme") === "dark" : this.getAttribute("data-theme") ? this.getAttribute("data-theme") === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
    const show = () => {
      button.innerHTML = dark() ? ICONS.sun : ICONS.moon;
      button.title = button.ariaLabel = dark() ? w.toLight : w.toDark;
    };
    try {
      const chosen = localStorage.getItem(THEME_SETTING);
      if (!forced() && (chosen === "light" || chosen === "dark")) this.setAttribute("data-theme", chosen);
    } catch {
      // storage unavailable; the machine's theme holds
    }
    show();
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", show);
    button.addEventListener("click", () => {
      const next = dark() ? "light" : "dark";
      this.setAttribute("data-theme", next);
      try {
        localStorage.setItem(THEME_SETTING, next);
      } catch {
        // storage unavailable; the choice holds for this page
      }
      show();
    });
  }

  /**
   * On a phone the open panel is exactly the visible part of the screen: when the keyboard comes up
   * (iOS shrinks only the visual viewport, and scrolls it to the field) the panel shrinks and follows,
   * so its head stays at the top and the field sits on the keyboard.
   */
  fitToTheScreen(on) {
    const screen = window.visualViewport;
    const panel = this.$(".panel");
    if (!screen) return;
    if (on && !this.fitting) {
      this.fitting = () => {
        panel.style.setProperty("--_vv-h", `${Math.round(screen.height)}px`);
        panel.style.setProperty("--_vv-top", `${Math.round(screen.offsetTop)}px`);
        // The lines keep their last one in view as the panel gets shorter.
        const lines = this.$(".body .lines");
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

  // A widget taken off the page (a language swap puts a fresh one in its place) lets the page go.
  disconnectedCallback() {
    this.dot?.close();
    if (this.heldAt === undefined) return;
    this.$(".panel").hidden = true;
    this.holdPage();
  }

  toggle() {
    const panel = this.$(".panel");
    if (panel.hidden) {
      panel.hidden = false;
      this.holdPage();
      this.dispatchEvent(new CustomEvent("pinecall:open"));
    } else {
      this.hide();
    }
  }

  /**
   * While the panel covers the page (a phone's full screen, or maximized), the page under it holds
   * still: a tap or a scroll in the panel never moves it, and on iOS focusing the field does not
   * slide it either. Closed or made small again, the page is back where it was.
   */
  holdPage() {
    const panel = this.$(".panel");
    const covers = !panel.hidden && (matchMedia("(max-width: 520px)").matches || panel.classList.contains("maxed"));
    this.$(".scrim").hidden = !covers;
    this.fitToTheScreen(!panel.hidden && matchMedia("(max-width: 520px)").matches);
    const body = document.body;
    if (covers && this.heldAt === undefined) {
      this.heldAt = window.scrollY;
      this.bodyWas = body.getAttribute("style");
      Object.assign(body.style, { position: "fixed", top: `-${this.heldAt}px`, left: "0", right: "0", width: "100%", overflow: "hidden" });
    } else if (!covers && this.heldAt !== undefined) {
      if (this.bodyWas === null) body.removeAttribute("style");
      else body.setAttribute("style", this.bodyWas);
      window.scrollTo(0, this.heldAt);
      this.heldAt = undefined;
    }
  }

  /**
   * `autostart`: request the microphone inside the opening click (browsers require a user
   * gesture), then release it; the room later gets its own track. On refusal, show the menu
   * with the reason.
   */
  async start() {
    const panel = this.$(".panel");
    if (!panel.hidden) return this.hide();
    panel.hidden = false;
    this.holdPage();
    this.dispatchEvent(new CustomEvent("pinecall:open"));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
    } catch (refused) {
      this.menu();
      this.notice(this.words.micRefused(refused.name ?? "refused"));
      return;
    }
    await this.conversation("talk");
  }

  async hide() {
    await this.hungUp();
    await this.leave();
    this.$(".panel").hidden = true;
    this.holdPage();
    this.menu();
  }

  showTools() {
    try {
      return localStorage.getItem(TOOLS_SETTING) === "1";
    } catch {
      return false;
    }
  }

  // ── views ─────────────────────────────────────────────────────────────────────

  menu() {
    this.$(".panel").classList.remove("wide");
    const body = this.$(".body");
    const kept = this.kept();
    const w = this.words;
    // The ways in come first and weigh the same whatever is kept below them; what was said before is
    // a quieter list under them, its last three in view and the rest one tap away.
    const action = (kind, icon, label, hint) => `<button class="action ${kind}" type="button" title="${hint}"><span class="action-icon">${icon}</span><span>${label}</span></button>`;
    const calls = this.byCode() || this.phone;
    body.innerHTML = `
      ${this.greeting ? `<p class="greeting"></p>` : ""}
      <div class="actions${calls ? "" : " two"}">
        ${calls ? action("call", ICONS.phone, w.callShort, this.byCode() ? w.callUsByCode : this.phone) : ""}
        ${action("talk", ICONS.mic, w.talkShort, w.talkSub(this.name))}
        ${action("chat", ICONS.chat, w.chatShort, w.chatSub(this.name))}
      </div>
      ${kept.length > 0 ? `<div class="kept-head"><span>${w.recent}</span><button class="forget" type="button">${w.clear}</button></div>` : ""}
      <div class="recent">${kept.map((one, at) => `<button class="recent-row" type="button" data-at="${at}"${at >= RECENT_IN_VIEW ? " hidden" : ""}><span class="recent-icon">${one.scope === "talk" ? ICONS.phone : ICONS.chat}</span><span class="recent-text"></span><span class="recent-when"></span></button>`).join("")}</div>
      ${kept.length > RECENT_IN_VIEW ? `<button class="recent-more" type="button">${w.seeAll(kept.length)}</button>` : ""}`;
    this.$("footer").innerHTML = `<span class="status">${[this.company, w.answersNow(this.name)].filter(Boolean).join(" · ")}</span>`;
    // Set as text, never HTML: the greeting is the page's, the lines are what was said.
    const greeting = body.querySelector(".greeting");
    if (greeting) greeting.textContent = this.greeting;
    for (const row of body.querySelectorAll(".recent-row")) {
      const one = kept[Number(row.dataset.at)];
      const first = one.lines.find((line) => line.who === "user") ?? one.lines[0];
      row.querySelector(".recent-text").textContent = first?.text ?? (one.scope === "talk" ? w.aCall : w.aChat);
      row.querySelector(".recent-when").textContent = when(one.started_at, w);
      row.addEventListener("click", () => this.review(one));
    }
    const more = body.querySelector(".recent-more");
    more?.addEventListener("click", () => {
      const showing = more.dataset.all === "1";
      for (const row of body.querySelectorAll(".recent-row")) row.hidden = !showing ? false : Number(row.dataset.at) >= RECENT_IN_VIEW;
      more.dataset.all = showing ? "" : "1";
      more.textContent = showing ? w.seeAll(kept.length) : w.seeFewer;
    });
    body.querySelector(".forget")?.addEventListener("click", () => this.forgetAll());
    body.querySelector(".action.call")?.addEventListener("click", () => this.callUs());
    body.querySelector(".action.talk").addEventListener("click", () => this.conversation("talk"));
    body.querySelector(".action.chat").addEventListener("click", () => this.conversation("chat"));
  }

  /**
   * One kept conversation read again, as it was said. One the gateway gave a resume token is carried
   * on from here: a line written, or the call taken up again. A new one of the same kind starts too.
   */
  review(one) {
    this.viewing = one.call;
    this.$(".panel").classList.add("wide");
    const body = this.$(".body");
    const w = this.words;
    const writes = Boolean(one.resume) && one.scope === "chat";
    body.innerHTML = `<span class="status"></span><ul class="lines"></ul>
      ${writes ? `<div class="row"><input type="text" placeholder="${w.writeOn}" autocomplete="off"><button class="btn send" aria-label="${w.send}">${ICONS.send}</button></div>` : ""}`;
    const lines = body.querySelector(".lines");
    for (const line of one.lines) {
      const item = document.createElement("li");
      item.className = line.who === "user" ? "user" : "agent";
      item.textContent = line.text;
      lines.append(item);
    }
    const started = new Date(one.started_at);
    this.status(`${one.scope === "talk" ? this.words.call : this.words.chat} · ${started.toLocaleDateString(undefined, { day: "numeric", month: "short" })}, ${started.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}${one.ended_at === null ? "" : ` · ${this.words.ended}`}`);
    this.footer(null, one.scope);
    this.renderSide();
    lines.scrollTop = lines.scrollHeight;
    // In the body, not the foot: on a phone and when maximized the foot is not drawn.
    if (one.resume && one.scope === "talk") {
      body.insertAdjacentHTML("beforeend", `<div class="row carry-row"><button class="btn carry" type="button">${w.continueCall}</button></div>`);
      body.querySelector(".carry").addEventListener("click", () => this.conversation("talk", one));
    }
    if (writes) {
      const input = body.querySelector("input");
      const carry = () => {
        const text = input.value.trim();
        if (text) this.conversation("chat", one, text);
      };
      body.querySelector(".send").addEventListener("click", carry);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") carry();
      });
      input.focus();
    }
  }

  /** Footer for non-menu views: back, the tools toggle (with a log), and new/end for calls and chats. */
  footer(end, scope = null) {
    const footer = this.$("footer");
    const w = this.words;
    footer.innerHTML = `
      <button class="back">${ICONS.back}${w.back}</button>
      <span class="right">
        ${this.logUrl ? `<label class="toggle"><input type="checkbox" ${this.showTools() ? "checked" : ""}> ${w.showTools}</label>` : ""}
        ${scope ? `<button class="btn quiet again">${scope === "talk" ? w.newCall : w.newChat}</button>` : ""}
        ${end ? `<button class="btn danger end">${end}</button>` : ""}
      </span>`;
    footer.querySelector(".back").addEventListener("click", async () => {
      await this.leave();
      this.menu();
    });
    footer.querySelector(".toggle input")?.addEventListener("change", (event) => {
      try {
        localStorage.setItem(TOOLS_SETTING, event.target.checked ? "1" : "0");
      } catch {
        // storage unavailable; the toggle still works for this page
      }
      this.transcript?.tools(event.target.checked);
    });
    footer.querySelector(".end")?.addEventListener("click", () => this.leave(true));
    footer.querySelector(".again")?.addEventListener("click", () => this.again(scope));
  }

  /** Hang up the current session and start a new one on a fresh token. */
  async again(scope) {
    await this.hungUp();
    await this.leave();
    await this.conversation(scope);
  }

  /**
   * Tell the agent the visitor hung up. A reload and a hang-up both leave the room alike, and a call
   * whose visitor left waits for them to come back: said, it ends at once instead. Said at the
   * gateway's door first, over HTTP with the call's own token and `keepalive`, which a closing tab
   * still completes; the room's data channel says it too, for a gateway of the version before, but a
   * seat that leaves as it publishes loses that one with the room more often than not.
   */
  async hungUp() {
    const door = this.hangup;
    this.hangup = null;
    if (door) {
      const said = `${this.gateway}/v1/calls/${encodeURIComponent(door.call)}/hangup?token=${encodeURIComponent(door.token)}`;
      fetch(said, { method: "POST", keepalive: true }).catch(() => undefined);
    }
    const room = this.room;
    if (!room) return;
    // Never waited on for long: a data channel that does not answer must not hold the hang-up.
    const said = room.localParticipant.publishData(new TextEncoder().encode("{}"), { topic: HANGUP, reliable: true });
    try {
      await Promise.race([said, new Promise((resolve) => setTimeout(resolve, 1200))]);
    } catch {
      // Said or not, the room is left; unsaid, the call waits for the visitor and then ends.
    }
  }

  /** Whether "Call us" uses a code. */
  byCode() {
    return Boolean(this.codeUrl || this.codeProvider);
  }

  /** Fetch {code, number, expires_at, code_token} from `codeProvider` or `code-url`. */
  async askCode() {
    if (this.codeProvider) return this.codeProvider(this.agent);
    const answer = await fetch(this.codeUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: this.agent }),
    });
    const said = await answer.json().catch(() => ({}));
    if (!answer.ok) throw new Error(said.detail ?? `code: HTTP ${answer.status}`);
    return said;
  }

  /**
   * "Call us" with a code: long-poll the gateway with the code token (up to 25 s per request)
   * until a call claims it, then follow that call's log with the returned log token.
   */
  async callByCode() {
    this.$(".panel").classList.add("wide");
    const body = this.$(".body");
    body.innerHTML = `<span class="status">${this.words.gettingCode}</span><ul class="lines"></ul>`;
    this.footer(null);
    let code;
    try {
      code = await this.askCode();
      if (!(typeof code?.code === "string" && typeof code.number === "string" && typeof code.code_token === "string"))
        throw new Error("the code endpoint answered with something this widget does not know");
    } catch (refused) {
      this.status(refused.message, "failed");
      return;
    }
    const tel = code.number.replace(/[^\d+]/g, "");
    body.innerHTML = `
      <div class="dial">
        <div class="step">
          <span class="n">1</span><span class="say">${this.words.callName(this.name)}</span>
          <div class="number"><b></b><a>${ICONS.phone}${this.words.dial}</a></div>
        </div>
        <div class="step">
          <span class="n">2</span><span class="say">${this.words.keyCode} <small>· ${this.words.anyTime}</small></span>
          <div class="digits" role="img"></div>
        </div>
        <div class="waiting"><span class="status"></span><span class="expires"></span></div>
      </div>
      <div class="soon">${this.words.showsHere}</div>
      <ul class="lines" hidden></ul>`;
    // From the application's server: set as text, never HTML.
    body.querySelector(".number b").textContent = spaced(code.number);
    body.querySelector(".number a").href = `tel:${tel}`;
    const digits = body.querySelector(".digits");
    for (const digit of String(code.code)) digits.append(Object.assign(document.createElement("span"), { textContent: digit }));
    digits.setAttribute("aria-label", this.words.theCode(String(code.code).split("").join(" ")));
    this.status(this.words.waiting);
    const expires = body.querySelector(".expires");
    const waiting = () => {
      const left = Math.max(0, Math.floor(code.expires_at - Date.now() / 1000));
      expires.textContent = this.words.expiresIn(`${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`);
    };
    waiting();
    this.codeClock = setInterval(waiting, 1000);
    const stop = new AbortController();
    this.codeWait = stop;
    const asked = `${this.gateway}/v1/codes/${encodeURIComponent(code.code)}?wait=1&token=${encodeURIComponent(code.code_token)}`;
    while (!stop.signal.aborted) {
      let standing;
      try {
        const answer = await fetch(asked, { signal: stop.signal });
        // Retry on 5xx and network errors; any other status is final.
        if (answer.status >= 500) throw new Error(`code: HTTP ${answer.status}`);
        standing = await answer.json();
        if (!answer.ok) throw Object.assign(new Error(standing.detail ?? `code: HTTP ${answer.status}`), { final: true });
      } catch (failed) {
        if (stop.signal.aborted) return;
        if (failed.final) return this.codeFailed(failed.message);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        continue;
      }
      if (standing.status === "claimed") return this.followClaimed(standing);
      if (standing.status === "expired") return this.codeFailed(this.words.codeExpired, true);
    }
  }

  /** Follow the claimed call's log from the gateway. */
  followClaimed(standing) {
    clearInterval(this.codeClock);
    this.codeClock = null;
    this.$(".body .dial")?.remove();
    this.$(".body .soon")?.remove();
    const lines = this.$(".body .lines");
    lines.hidden = false;
    lines.insertAdjacentHTML("beforebegin", `<span class="status"></span>`);
    this.status(this.words.onTheLine(this.name), "live");
    this.transcript = new Transcript(lines, () => this.showTools(), this.words);
    this.hangup = { call: standing.call, token: standing.log_token };
    const call = encodeURIComponent(standing.call);
    this.transcript.follow(
      `${this.gateway}/v1/calls/${call}/events?types=${LOG_TYPES}&after=0&token=${encodeURIComponent(standing.log_token)}`,
    );
    this.transcript.mark(this.words.yourCall, true);
  }

  /** Show why the code failed; offer a new one if it expired. */
  codeFailed(said, again = false) {
    clearInterval(this.codeClock);
    this.codeClock = null;
    this.status(said, "failed");
    if (again) this.notice(this.words.newCode, () => this.callByCode());
  }

  /** "Call us": the number and the live call from log-url, or the code flow when configured. */
  callUs() {
    if (this.byCode()) return this.callByCode();
    this.$(".panel").classList.add("wide");
    const tel = this.phone.replace(/[^\d+]/g, "");
    this.$(".body").innerHTML = `
      <div class="number"><b>${this.phone}</b><a href="tel:${tel}">${this.words.dial}</a></div>
      <span class="status">${this.logUrl ? this.words.waitingDots : this.words.callTheNumber(this.name)}</span>
      <ul class="lines"></ul>`;
    this.footer(null);
    if (!this.logUrl) return;
    this.transcript = new Transcript(this.$(".lines"), () => this.showTools(), this.words);
    const openedAt = Date.now() / 1000 - 5;
    let showing = null;
    const poll = async () => {
      try {
        const answer = await fetch(this.log("list=1"));
        if (!answer.ok) throw new Error(`log: HTTP ${answer.status}`);
        const { calls } = await answer.json();
        const live = calls.find((call) => call.live);
        this.status(live ? this.words.onTheLine(this.name) : this.words.waitingDots, live ? "live" : "");
        const current = live ?? calls.find((call) => (call.started_at ?? 0) >= openedAt);
        if (current && showing !== current.call) {
          showing = current.call;
          this.transcript.follow(this.log(`call=${encodeURIComponent(current.call)}`));
          this.transcript.mark(this.words.callFrom(current.from), true);
        }
      } catch (failed) {
        this.status(failed.message, "failed");
      }
    };
    // Poll every second while the phone rings.
    poll();
    this.phonePoll = setInterval(poll, 1000);
  }

  /** A conversation: a new one, or `earlier` carried on, its first line `first` when one was written. */
  async conversation(scope, earlier = null, first = null) {
    this.viewing = null;
    this.$(".panel").classList.add("wide");
    const body = this.$(".body");
    body.innerHTML = `
      ${this.greeting && !earlier ? `<p class="greeting"></p>` : ""}
      <span class="status">${this.words.connecting}</span>
      <ul class="lines"></ul>
      ${scope === "chat" ? `<div class="row"><input type="text" placeholder="${this.words.writeTo(this.name)}" autocomplete="off"><button class="btn send" aria-label="${this.words.send}">${ICONS.send}</button></div>` : ""}`;
    body.querySelector(".greeting")?.replaceChildren(document.createTextNode(this.greeting));
    // What was said before, as it was kept: drawn now, and again by the log's reader when it starts.
    for (const line of earlier?.lines ?? []) this.draw(`earlier_${line.key}`, line.who === "user" ? "user" : "agent", line.text, true, false);
    this.footer(scope === "talk" ? this.words.hangUp : this.words.endChat, scope);
    if (scope === "chat") {
      const input = body.querySelector("input");
      const send = async () => {
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        const pending = this.logUrl ? null : `typed_${Date.now()}`;
        if (pending) this.draw(pending, "user interim", text, false);
        try {
          if (!this.room) await this.open("chat", this.current ?? earlier);
          this.transcript?.typed(text);
          await this.send(text);
          if (pending) this.draw(pending, "user", text, true);
        } catch (failed) {
          this.transcript?.untyped();
          if (pending) this.streamLines.get(pending)?.remove();
          input.value = text;
          this.status(failed.message, "failed");
        }
        input.focus();
      };
      body.querySelector(".send").addEventListener("click", send);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") send();
      });
    }
    try {
      await this.open(scope, earlier);
    } catch (failed) {
      this.status(failed.message, "failed");
      return;
    }
    if (first && scope === "chat") {
      const input = body.querySelector("input");
      input.value = first;
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    }
  }

  // ── room ──────────────────────────────────────────────────────────────────────

  async token(scope, resume = null) {
    // `tokenProvider(scope, agent, resume)` replaces token-url for pages that mint tokens themselves.
    if (typeof this.tokenProvider === "function") return this.tokenProvider(scope, this.agent, resume ?? undefined);
    const url = this.getAttribute("token-url");
    if (!url) throw new Error("pinecall-widget: token-url is missing");
    if (!this.agent) throw new Error("pinecall-widget: agent is missing");
    const answer = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: this.agent, scope, ...(resume ? { resume } : {}) }),
    });
    const minted = await answer.json().catch(() => ({}));
    if (!answer.ok) throw new Error(minted.detail ?? `token endpoint: HTTP ${answer.status}`);
    if (typeof minted?.server_url !== "string" || typeof minted?.participant_token !== "string")
      throw new Error("the token endpoint answered with something this widget does not know");
    return minted;
  }

  async open(scope, earlier = null) {
    await this.leave();
    this.streamLines.clear();
    const minted = await this.token(scope, earlier?.resume ?? null);
    // What a hang-up is said with at the gateway's door: the call and a token of its own.
    this.hangup = { call: minted.call, token: minted.log_token ?? minted.participant_token };
    const room = new Room();
    this.room = room;
    this.greeted = new Promise((resolve) => {
      this.onGreeted = resolve;
    });
    if (this.logUrl) {
      this.transcript = new Transcript(this.$(".lines"), () => this.showTools(), this.words);
      this.transcript.onAgent = () => this.onGreeted?.();
      this.transcript.onEnd = () => this.status(this.words.endedDot);
      this.transcript.onLine = (key, who, text) => this.kept_line(key, who, text);
      // Back in the same call, its log reads its own lines again: only the calls before it are drawn.
      const own = `${minted.call}:`;
      this.transcript.earlier = (earlier?.lines ?? []).filter((one) => !String(one.key).startsWith(own));
    } else {
      room.registerTextStreamHandler(TRANSCRIPTION, (reader, from) => this.read(reader, from.identity));
    }
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (scope !== "talk" || track.kind !== Track.Kind.Audio) return;
      const element = track.attach();
      element.style.display = "none";
      this.shadowRoot.append(element);
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((element) => element.remove()));
    room.on(RoomEvent.DataReceived, (payload, _from, _kind, topic) => {
      if (topic === UI) this.ui(payload);
    });
    room.on(RoomEvent.Disconnected, () => {
      // A replaced room disconnects after the new session is shown; only emit its end event.
      if (this.room === room) {
        this.room = null;
        this.status(this.words.endedDot);
      }
      if (this.current?.call === minted.call) this.ended();
      this.dispatchEvent(new CustomEvent("pinecall:ended", { detail: { call: minted.call } }));
    });
    await room.connect(minted.server_url, minted.participant_token);
    this.began(minted.call, scope, minted.resume_token ?? null, earlier);
    // The call exists only after the join, so follow its log now.
    if (this.logUrl) this.transcript.follow(this.log(`call=${encodeURIComponent(minted.call)}`));
    this.$(".body .greeting")?.remove();
    if (scope === "talk") {
      await room.localParticipant.setMicrophoneEnabled(true);
      // Autoplay may be blocked: with `autostart` the user gesture is several awaits back.
      if (!room.canPlaybackAudio) this.notice(this.words.tapToHear, () => room.startAudio());
    }
    this.status(scope === "talk" ? this.words.listening(this.name) : this.words.live, "live");
    this.dispatchEvent(new CustomEvent("pinecall:started", { detail: { call: minted.call, scope } }));
    return minted.call;
  }

  /**
   * Tell the agent what the visitor did on the page: `{name, data}` on pinecall.event. The agent's
   * onEvent runs when its class accepts the name from a participant; the runtime drops any other.
   */
  async event(name, data = {}) {
    if (this.dot) return this.dot.event(name, data);
    if (!this.room) throw new Error("not in a call");
    await this.room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({ name, data })), {
      topic: EVENT,
      reliable: true,
    });
  }

  async send(text) {
    if (!this.room) throw new Error("not connected");
    // Text sent before the agent joins is lost; wait for the greeting (max 8 s).
    await Promise.race([this.greeted, new Promise((resolve) => setTimeout(resolve, 8000))]);
    await this.room.localParticipant.sendText(text, { topic: CHAT });
  }

  /**
   * Leave the room, log stream and phone poll. On hang-up (`ended`) say so first, keep reading the
   * log so the final turns still show, and do not wait for the disconnect. Left otherwise, the call
   * waits for the visitor, who may carry it on from the conversations kept.
   */
  async leave(ended = false) {
    if (ended) await this.hungUp();
    this.hangup = null;
    const room = this.room;
    this.room = null;
    clearInterval(this.phonePoll);
    this.phonePoll = null;
    this.codeWait?.abort();
    this.codeWait = null;
    clearInterval(this.codeClock);
    this.codeClock = null;
    if (ended) {
      this.status(this.words.hangingUp);
      const end = this.$("footer .end");
      if (end) end.disabled = true;
      const input = this.$(".body input");
      if (input) input.disabled = true;
    } else {
      this.transcript?.stop();
      this.transcript = null;
    }
    await Promise.race([room?.disconnect(), new Promise((resolve) => setTimeout(resolve, 3000))]);
    if (ended) this.status(this.words.endedDot);
  }

  // ── transcripts from LiveKit text streams (no log-url) ────────────────────────

  async read(reader, identity) {
    const id = reader.info.attributes?.[SEGMENT_ID] ?? reader.info.id;
    const who = this.room?.remoteParticipants.get(identity)?.kind === ParticipantKind.AGENT ? "agent" : "user";
    if (who === "agent") this.onGreeted?.();
    let text = "";
    for await (const chunk of reader) {
      text += chunk;
      this.draw(id, who, text, false);
    }
    this.draw(id, who, text, reader.info.attributes?.[TRANSCRIPTION_FINAL] === "true");
  }

  /** Something the agent put on the screen: buttons to choose from, or a card of HTML. */
  ui(payload) {
    let data;
    try {
      data = JSON.parse(new TextDecoder().decode(payload));
    } catch {
      return;
    }
    const list = this.$(".lines");
    if (!list || !data || typeof data !== "object") return;
    const item = document.createElement("li");
    item.className = "agent card";
    if (data.type === "choices" && Array.isArray(data.options)) {
      if (typeof data.text === "string" && data.text) {
        const said = document.createElement("p");
        said.textContent = data.text;
        item.append(said);
      }
      const row = document.createElement("div");
      row.className = "choices";
      for (const option of data.options.slice(0, 24)) {
        const label = typeof option === "string" ? option : String(option?.label ?? "");
        if (!label) continue;
        const value = typeof option === "object" && typeof option?.value === "string" ? option.value : label;
        const choice = document.createElement("button");
        choice.type = "button";
        choice.className = "choice";
        choice.textContent = label;
        choice.addEventListener("click", async () => {
          for (const other of row.querySelectorAll("button")) other.disabled = true;
          choice.classList.add("chosen");
          await this.choose(value);
        });
        row.append(choice);
      }
      item.append(row);
    } else if (data.type === "html" && typeof data.html === "string") {
      item.append(safeHtml(data.html));
    } else {
      return;
    }
    list.append(item);
    list.scrollTop = list.scrollHeight;
  }

  /** A choice tapped is the visitor's next line, said as they would type it. */
  async choose(text) {
    if (!this.room) return;
    const pending = this.logUrl ? null : `typed_${Date.now()}`;
    if (pending) this.draw(pending, "user interim", text, false);
    this.transcript?.typed(text);
    try {
      await this.send(text);
      if (pending) this.draw(pending, "user", text, true);
    } catch (failed) {
      this.transcript?.untyped();
      if (pending) this.streamLines.get(pending)?.remove();
      this.status(failed.message, "failed");
    }
  }

  draw(id, who, text, final, keeps = true) {
    const list = this.$(".lines");
    if (!list) return;
    let line = this.streamLines.get(id);
    if (!line) {
      line = document.createElement("li");
      this.streamLines.set(id, line);
      list.append(line);
    }
    line.className = `${who}${final ? "" : " interim"}`;
    line.textContent = text;
    list.scrollTop = list.scrollHeight;
    if (final && keeps) this.kept_line(id, who, text);
  }

  /** Show a notice under the status, as a button when `tap` is given. */
  notice(text, tap) {
    const body = this.$(".body");
    if (!body) return;
    const line = document.createElement(tap ? "button" : "span");
    line.className = tap ? "btn quiet" : "status failed";
    line.textContent = text;
    if (tap) {
      line.addEventListener("click", async () => {
        await tap();
        line.remove();
      });
    }
    body.prepend(line);
  }

  status(text, tone = "") {
    const status = this.$(".body .status");
    if (!status) return;
    status.textContent = text;
    status.className = `status ${tone}`;
  }
}

if (!customElements.get("pinecall-widget")) customElements.define("pinecall-widget", PinecallWidget);
