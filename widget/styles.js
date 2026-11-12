// The look of <pinecall-widget>: ink, cream and rules, the page's own font, corners barely rounded.
// Every colour is a `--pc-*` property the page may set, in either theme; the dark palette is the
// same look turned over. The phone rules make the panel exactly the visible part of the screen,
// so iOS's keyboard shrinks it instead of sliding its head away.

export const PHONE = "(max-width: 520px)";

// The dark palette, for `theme="dark"`, and for `auto` on a dark machine unless the visitor chose
// light. A property the page set still wins.
const DARK = `
    color-scheme: dark;
    --_ink: var(--pc-ink, #f1ede6); --_accent: var(--pc-accent, #f1ede6); --_on-accent: var(--pc-on-accent, #1a1917);
    --_surface: var(--pc-surface, #1b1a18); --_raised: var(--pc-accent-soft, #2a2825); --_head: var(--pc-header-bg, #222120);
    --_line: var(--pc-line, #36332f); --_muted: var(--pc-muted, #a29c93); --_live: #5cc08a; --_failed: #e2685d;
    --_field: #1f1e1c; --_field-line: rgb(255 255 255 / .1); --_field-focus: rgb(255 255 255 / .3); --_field-dot: rgb(255 255 255 / .3);
    --_heard: #3a3522; --_hover: rgb(255 255 255 / .06); --_shadow: rgba(0, 0, 0, .5);
`;

export const STYLE = `
  :host { all: initial; display: contents; color-scheme: light; font-family: var(--pc-font, inherit); font-size: var(--pc-font-size, 15px); line-height: 1.5;
    color: var(--_ink);
    --_ink: var(--pc-ink, #1a1917); --_accent: var(--pc-accent, #1a1917); --_on-accent: var(--pc-on-accent, #fff);
    --_surface: var(--pc-surface, #fff); --_raised: var(--pc-accent-soft, #f6efe2); --_head: var(--pc-header-bg, #faf8f5);
    --_line: var(--pc-line, #e7e2da); --_muted: var(--pc-muted, #6f6a63); --_live: #2f8f5b; --_failed: #b3352b;
    --_field: #fff; --_field-line: rgb(0 0 0 / .08); --_field-focus: rgb(0 0 0 / .28); --_field-dot: rgb(0 0 0 / .25);
    --_heard: #fffbe8; --_hover: rgb(0 0 0 / .05); --_shadow: rgba(26, 25, 23, .18);
    --_radius: var(--pc-radius, 4px); --_offset: var(--pc-offset, 20px); --_z: var(--pc-z, 2147483000); --_accent-ink: var(--_accent); }
  :host([theme="dark"]), :host([data-theme="dark"]) { ${DARK} }
  @media (prefers-color-scheme: dark) { :host(:not([theme="light"]):not([data-theme="light"])) { ${DARK} } }
  :host([position="inline"]) { display: inline-block; }
  * { box-sizing: border-box; }
  button { font: inherit; }
  [hidden] { display: none !important; }
  .fab { position: fixed; right: var(--_offset); bottom: var(--_offset); z-index: var(--_z); display: inline-flex; align-items: center; justify-content: center; gap: 9px;
         min-width: 54px; height: 54px; padding: var(--pc-button-padding, 0); border: var(--pc-button-border, 0); border-radius: var(--pc-button-radius, 999px);
         background: var(--pc-button-bg, var(--_accent)); color: var(--pc-button-ink, var(--_on-accent)); cursor: pointer;
         font-weight: var(--pc-button-weight, 500); font-size: var(--pc-button-font-size, inherit); box-shadow: var(--pc-button-shadow, 0 4px 16px rgba(0,0,0,.2)); }
  .fab.labelled { padding: var(--pc-button-padding, 0 22px 0 18px); }
  .fab .icon { display: inline-flex; }
  .fab svg { width: 26px; height: 26px; }
  .fab.labelled svg { width: 22px; height: 22px; }
  :host([position="inline"]) .fab { position: static; }
  /* Minimized on a phone, the agent's newest line waits over the launcher; a tap opens the chat again. */
  .peek { position: fixed; right: var(--_offset); bottom: calc(var(--_offset) + 64px); z-index: var(--_z); max-width: min(300px, calc(100vw - 2 * var(--_offset)));
          display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border: 0; border-radius: 14px; border-bottom-right-radius: 4px; text-align: left;
          background: var(--_surface); color: var(--_ink); box-shadow: 0 8px 28px var(--_shadow), 0 0 0 1px var(--_line); cursor: pointer; animation: k-in .18s ease; }
  .peek-who { font-size: 11px; font-weight: 500; letter-spacing: .14em; text-transform: uppercase; color: var(--_muted); }
  .peek-text { font-size: 14px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .panel { position: fixed; right: var(--_offset); bottom: calc(var(--_offset) + 64px); z-index: var(--_z);
           width: min(var(--pc-panel-width, 400px), calc(100vw - 2 * var(--_offset))); height: min(var(--pc-panel-height, 640px), calc(100vh - 110px));
           display: flex; flex-direction: column; background: var(--_surface); border-radius: var(--_radius); overflow: hidden;
           box-shadow: 0 24px 64px var(--_shadow), 0 0 0 1px var(--_line); transform-origin: bottom right; animation: k-in .18s cubic-bezier(.2,.8,.2,1); }
  .panel.sized { width: min(var(--_w), calc(100vw - 2 * var(--_offset))); height: min(var(--_h), calc(100vh - 2 * var(--_offset) - 64px)); }
  .panel.maxed { inset: 0 !important; width: auto !important; height: auto !important; border-radius: 0; box-shadow: none; }
  .panel.sizing { animation: none; user-select: none; }
  @keyframes k-in { from { opacity: 0; transform: translateY(8px) scale(.98); } to { opacity: 1; transform: none; } }
  :host([position="bottom-left"]) .fab, :host([position="bottom-left"]) .panel, :host([position="bottom-left"]) .peek { right: auto; left: var(--_offset); }
  :host([position="top-right"]) .fab { bottom: auto; top: var(--_offset); }
  :host([position="top-left"]) .fab { right: auto; bottom: auto; left: var(--_offset); top: var(--_offset); }
  :host([position^="top"]) .panel, :host([position^="top"]) .peek { bottom: auto; top: calc(var(--_offset) + 64px); }
  :host([position="top-left"]) .panel, :host([position="top-left"]) .peek { right: auto; left: var(--_offset); }
  :host([position="bottom-left"]) .panel { transform-origin: bottom left; }
  :host([position="top-right"]) .panel { transform-origin: top right; }
  :host([position="top-left"]) .panel { transform-origin: top left; }
  :host([position$="left"]) .peek { border-bottom-right-radius: 14px; border-bottom-left-radius: 4px; }
  /* The panel is sized from the edges that face the page: the side for its width, the top (the
     bottom, when it opens from the top) for its height, the corner for both. */
  .edge { position: absolute; z-index: 3; touch-action: none; }
  .edge::after { content: ""; position: absolute; background: var(--_accent); opacity: 0; transition: opacity .12s; }
  .edge:hover::after, .panel.sizing .edge.held::after { opacity: .6; }
  .edge-x { top: 14px; bottom: 14px; left: 0; width: 7px; cursor: ew-resize; } .edge-x::after { top: 0; bottom: 0; left: 0; width: 2px; }
  .edge-y { left: 14px; right: 14px; top: 0; height: 7px; cursor: ns-resize; } .edge-y::after { left: 0; right: 0; top: 0; height: 2px; }
  .grip { top: 0; left: 0; width: 14px; height: 14px; cursor: nwse-resize; }
  .grip::after { top: 0; left: 0; width: 10px; height: 10px; background: none; border-top: 2px solid var(--_accent); border-left: 2px solid var(--_accent); }
  :host([position$="left"]) .edge-x, :host([position$="left"]) .edge-x::after { left: auto; right: 0; }
  :host([position^="top"]) .edge-y, :host([position^="top"]) .edge-y::after { top: auto; bottom: 0; }
  :host([position="bottom-left"]) .grip { left: auto; right: 0; cursor: nesw-resize; }
  :host([position="bottom-left"]) .grip::after { left: auto; right: 0; border-left: 0; border-right: 2px solid var(--_accent); }
  :host([position="top-right"]) .grip { top: auto; bottom: 0; cursor: nesw-resize; }
  :host([position="top-right"]) .grip::after { top: auto; bottom: 0; border-top: 0; border-bottom: 2px solid var(--_accent); }
  :host([position="top-left"]) .grip { top: auto; bottom: 0; left: auto; right: 0; }
  :host([position="top-left"]) .grip::after { top: auto; bottom: 0; left: auto; right: 0; border: 0; border-bottom: 2px solid var(--_accent); border-right: 2px solid var(--_accent); }
  .panel.maxed .edge, :host([position="inline"]) .edge, :host([position="inline"]) header .maximize { display: none; }
  .scrim { position: fixed; left: 0; right: 0; top: -100vh; height: 300vh; z-index: calc(var(--_z) - 1); background: var(--_surface); }
  header { position: relative; display: flex; align-items: center; gap: 10px; padding: 12px 10px 12px 16px; flex: 0 0 auto; border-bottom: 1px solid var(--_line); background: var(--_head); }
  header .avatar { position: relative; width: 38px; height: 38px; flex: 0 0 38px; border-radius: 50%; display: grid; place-items: center; background: var(--_accent); color: var(--_on-accent);
                   font-weight: 500; letter-spacing: .04em; }
  header .avatar::after { content: ""; position: absolute; right: -1px; bottom: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--_live); border: 2px solid var(--_head); }
  header .who { flex: 1 1 auto; min-width: 0; }
  header h2 { margin: 0; font-size: 12px; font-weight: 500; letter-spacing: .14em; text-transform: uppercase; line-height: 1.3; }
  header p { margin: 2px 0 0; font-size: 12.5px; color: var(--_muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tool { width: 34px; height: 34px; border: 0; border-radius: 50%; background: transparent; color: var(--_muted); cursor: pointer; display: grid; place-items: center; flex: 0 0 auto; }
  .tool svg { width: 18px; height: 18px; }
  .tool:hover { background: var(--_raised); color: var(--_ink); }
  header .tool.call { color: var(--_ink); }
  header .tool.call.on { background: var(--_accent); color: var(--_on-accent); }
  header .close { font-size: 22px; line-height: 1; }
  :host([theme="light"]) header .theme, :host([theme="dark"]) header .theme { display: none; }
  /* Which call, when the page offers both: in the browser, or from the visitor's phone. */
  .choose { position: absolute; top: calc(100% - 4px); right: 10px; z-index: 7; display: flex; flex-direction: column; min-width: 250px; max-width: calc(100% - 20px);
            padding: 6px; border-radius: 12px; background: var(--_surface); box-shadow: 0 8px 28px var(--_shadow), 0 0 0 1px var(--_line); animation: k-in .14s ease; }
  .choose button { display: flex; align-items: center; gap: 12px; padding: 10px; border: 0; border-radius: 8px; background: none; color: inherit; text-align: left; cursor: pointer; }
  .choose button:hover { background: var(--_raised); }
  .choose i { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; display: grid; place-items: center; background: var(--_accent); color: var(--_on-accent); }
  .choose i svg { width: 17px; height: 17px; }
  .choose b { display: block; font-size: 14px; font-weight: 500; line-height: 1.3; }
  .choose small { display: block; font-size: 12px; color: var(--_muted); }
  .body { position: relative; display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
  .status { flex: 0 0 auto; padding: 6px 16px 0; font-size: 12px; color: var(--_muted); display: flex; align-items: center; gap: 7px; min-height: 18px; }
  .status.live { color: var(--_live); }
  .status.live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--_live); }
  .status.failed { color: var(--_failed); }
  .lines { list-style: none; margin: 0; padding: 10px 16px 14px; display: flex; flex-direction: column; gap: 8px; flex: 1 1 auto; overflow-y: auto; overscroll-behavior: contain; }
  .lines li { padding: 9px 13px; border-radius: 14px; max-width: 86%; font-size: 14.5px; line-height: 1.45; overflow-wrap: anywhere; white-space: pre-line; }
  .lines li.agent { background: var(--_raised); align-self: flex-start; border-bottom-left-radius: 4px; }
  .lines li.user { background: var(--_accent); color: var(--_on-accent); align-self: flex-end; border-bottom-right-radius: 4px; }
  .lines li.interim { opacity: .6; }
  .lines li.mark { background: none; color: var(--_muted); font: 11.5px/1.4 ui-monospace, Menlo, monospace; max-width: 100%; padding: 2px 4px; }
  .lines li.typing { display: inline-flex; gap: 4px; align-items: center; padding: 13px 14px; }
  .lines li.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--_muted); animation: pc-dot 1.2s infinite ease-in-out; }
  .lines li.typing i:nth-child(2) { animation-delay: .2s; } .lines li.typing i:nth-child(3) { animation-delay: .4s; }
  @keyframes pc-dot { 0%, 80%, 100% { opacity: .35; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
  .said { display: block; white-space: normal; }
  .said p { margin: 0; } .said p + p, .said ul + p, .said p + ul { margin-top: 6px; }
  .said ul { margin: 4px 0 0; padding-left: 18px; } .said li { padding: 1px 0; max-width: none; background: none; border-radius: 0; font-size: inherit; white-space: normal; }
  .said b { font-weight: 600; } .said a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
  .lines li.card { max-width: 100%; padding: 0; background: none; white-space: normal; }
  .lines li.card > p { margin: 0 0 8px; }
  .choices { display: flex; flex-wrap: wrap; gap: 8px; }
  .choice { font: inherit; font-size: 13.5px; padding: 7px 13px; border-radius: 999px; border: 1px solid var(--_line); background: var(--_surface); color: inherit; cursor: pointer; }
  .choice:hover:not([disabled]) { border-color: var(--_accent); }
  .choice[disabled] { cursor: default; opacity: .45; }
  .choice.chosen { opacity: 1; background: var(--_accent); border-color: var(--_accent); color: var(--_on-accent); }
  .lines li.products { max-width: 100%; width: 100%; padding: 0; background: none; }
  .shelf { display: flex; gap: 8px; overflow-x: auto; scroll-snap-type: x mandatory; padding-bottom: 2px; overscroll-behavior-x: contain; }
  .shelf::-webkit-scrollbar { display: none; }
  .shelf.dealing { scroll-snap-type: none; }
  /* A card is the photo and three quiet lines under it: no box, no border. */
  .product { flex: 0 0 min(150px, 46%); scroll-snap-align: start; display: flex; flex-direction: column; gap: 1px; padding: 0; border: 0;
             background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .product .frame { position: relative; display: block; margin-bottom: 7px; border-radius: var(--_radius); overflow: hidden; }
  .product img { width: 100%; aspect-ratio: 4 / 5; object-fit: cover; display: block; background: var(--_raised); transition: transform .4s ease; }
  .product:hover:not([disabled]) img { transform: scale(1.03); }
  .product .zoom { position: absolute; right: 7px; bottom: 7px; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
                   background: rgb(255 255 255 / .82); color: #1a1917; backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); }
  .product .zoom svg { width: 14px; height: 14px; }
  .lines li.products .hint { margin: 6px 2px 0; font-size: 12px; color: var(--_muted); }
  .product { transition: opacity .5s ease, transform .5s cubic-bezier(.2, .8, .2, 1); }
  .product.dealing { opacity: 0; transform: translateX(24px) scale(.96); transition: none; }
  .product b { font-size: 13px; font-weight: 500; line-height: 1.3; padding: 0 1px; }
  .product span { font-size: 13px; padding: 0 1px; }
  .product small { font-size: 11.5px; color: var(--_muted); padding: 0 1px; }
  .lines li.products:has(.product:only-child) .product { flex-basis: min(220px, 70%); }
  .viewer { position: absolute; inset: 0; z-index: 5; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
            padding: 52px 16px 20px; background: rgb(20 18 16 / .9); color: #fff; opacity: 0; transition: opacity .18s ease; border-radius: inherit; }
  .viewer.on { opacity: 1; }
  .viewer img { max-width: 100%; max-height: calc(100% - 150px); object-fit: contain; border-radius: var(--_radius); transform: scale(.96); transition: transform .22s cubic-bezier(.2, .8, .2, 1); cursor: zoom-out; }
  .viewer.on img { transform: none; }
  .viewer p { margin: 0; font-size: 13.5px; text-align: center; }
  .viewer b { font-weight: 500; }
  .viewer-sheet { display: flex; flex-direction: column; align-items: center; gap: 10px; cursor: default; width: 100%; max-width: 340px; }
  .viewer-sizes { display: flex; gap: 8px; }
  .viewer-sizes button { min-width: 46px; height: 40px; padding: 0 12px; border: 1px solid rgb(255 255 255 / .45); border-radius: 999px; background: none;
                         color: #fff; font: inherit; font-size: 14px; cursor: pointer; }
  .viewer-sizes button[aria-checked="true"] { background: #fff; color: #1a1917; border-color: #fff; }
  .viewer-add { width: 100%; height: 46px; border: 0; border-radius: 999px; background: #fff; color: #1a1917; font: inherit; font-size: 14.5px; font-weight: 500; cursor: pointer; }
  .viewer-add:disabled { background: rgb(255 255 255 / .25); color: rgb(255 255 255 / .8); cursor: default; }
  .viewer-out { opacity: .8; }
  .viewer-close { position: absolute; top: 10px; right: 10px; width: 36px; height: 36px; border: 0; border-radius: 50%; background: rgb(255 255 255 / .14);
                  color: #fff; font-size: 24px; line-height: 1; cursor: pointer; }
  .viewer-close:hover { background: rgb(255 255 255 / .24); }
  /* The agent's form: a cream card, white fields, its choices as quiet rows. */
  .lines li.form { width: 100%; max-width: 100%; padding: 16px; background: var(--_raised); border-radius: 16px; white-space: normal; }
  .kf { display: grid; gap: 12px; margin: 0; }
  .kf-title { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.3; }
  .kf-field { display: grid; gap: 5px; margin: 0; }
  .kf-label { font-size: 12px; font-weight: 500; letter-spacing: .02em; color: var(--_muted); }
  .kf-input { width: 100%; height: 44px; margin: 0; padding: 0 14px; font: inherit; font-size: max(16px, 1em); color: var(--_ink); background: var(--_field);
              border: 1px solid var(--_field-line); border-radius: 12px; outline: none; -webkit-appearance: none; appearance: none;
              transition: border-color .15s ease, box-shadow .15s ease, background .3s ease; }
  .kf-input:focus { border-color: var(--_field-focus); box-shadow: 0 0 0 3px var(--_hover); }
  .kf-input.kf-missing, .kf-opts.kf-missing .kf-opt { border-color: var(--_failed); }
  .kf-input.kf-heard { background: var(--_heard); }
  .kf-opts { display: grid; gap: 6px; }
  .kf-opt { display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 8px 14px; background: var(--_field); border: 1px solid var(--_field-line); border-radius: 12px;
            cursor: pointer; font-size: 14px; transition: border-color .15s ease; }
  .kf-opt input { position: absolute; opacity: 0; pointer-events: none; }
  .kf-dot { flex: 0 0 18px; width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--_field-dot); display: grid; place-items: center; }
  .kf-dot::after { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--_accent); transform: scale(0); transition: transform .15s ease; }
  .kf-opt:has(input:checked), .kf-opt:has(input:checked) .kf-dot { border-color: var(--_accent); }
  .kf-opt:has(input:checked) .kf-dot::after { transform: scale(1); }
  .kf-opt-name { flex: 1 1 auto; }
  .kf-opt-cost { color: var(--_muted); font-size: 13px; white-space: nowrap; }
  .kf-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .kf-note { margin: 0; font-size: 12px; color: var(--_muted); }
  .kf-send, .pill { height: 46px; margin-top: 2px; border: 0; border-radius: 999px; background: var(--_accent); color: var(--_on-accent); font: inherit; font-size: 14.5px; font-weight: 500; cursor: pointer; }
  .kf-send:disabled { opacity: .6; cursor: default; }
  .toast { position: absolute; left: 50%; bottom: 84px; z-index: 6; transform: translate(-50%, 8px); max-width: calc(100% - 32px); padding: 10px 16px; border-radius: 999px;
           background: var(--_accent); color: var(--_on-accent); font-size: 13.5px; box-shadow: 0 6px 20px rgb(0 0 0 / .2); opacity: 0; transition: opacity .2s ease, transform .2s ease;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; pointer-events: none; }
  .toast.on { opacity: 1; transform: translate(-50%, 0); }
  .toast.failed { background: var(--_failed); color: #fff; }
  .html { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px solid var(--_line); border-radius: var(--_radius); background: var(--_surface); overflow-wrap: anywhere; }
  .html > * { margin: 0; }
  .html a { color: var(--_ink); text-decoration: underline; text-underline-offset: 2px; }
  .html img { max-width: 100%; height: auto; border-radius: var(--_radius); display: block; }
  .html table { border-collapse: collapse; font-size: 13px; }
  .html td, .html th { padding: 4px 8px; border-bottom: 1px solid var(--_line); text-align: left; }
  .notice { margin: 8px 16px 0; font-size: 13px; color: var(--_failed); }
  .notice.tap { color: var(--_ink); background: var(--_raised); border: 0; padding: 8px 12px; border-radius: var(--_radius); cursor: pointer; align-self: flex-start; }
  footer { display: flex; align-items: center; padding: 10px 12px 12px; flex: 0 0 auto; background: var(--_surface); }
  /* One field the whole width: the words, and inside it the microphone and the send. */
  .field { position: relative; display: flex; align-items: center; gap: 2px; flex: 1 1 auto; width: 100%; min-width: 0; min-height: 46px; padding: 0 5px 0 18px;
           border: 0; border-radius: 999px; background: var(--_raised); overflow: hidden; transition: background .2s ease; }
  .field:focus-within { background: color-mix(in srgb, var(--_raised) 80%, var(--_ink) 6%); }
  .field .mic { position: relative; width: 36px; height: 36px; flex: 0 0 36px; border: 0; border-radius: 50%; background: transparent; color: var(--_muted);
                display: grid; place-items: center; cursor: pointer; transition: color .15s ease, background .15s ease; }
  .field .mic:hover { color: var(--_ink); background: var(--_hover); }
  /* Dictating: the microphone is a stop, with a soft ring breathing to the voice. */
  .field[data-state="dictating"] .mic { color: #fff; background: var(--_failed); }
  .field[data-state="dictating"] .mic::after { content: ""; position: absolute; inset: -4px; border-radius: 50%; border: 2px solid var(--_failed);
                                               opacity: .35; transform: scale(var(--_level, 1)); transition: transform .08s linear; }
  .field[data-state="dictating"] .mic svg { width: 14px; height: 14px; }
  .field[data-state="settling"] .mic { opacity: .5; pointer-events: none; }
  .field input.heard { color: var(--_muted); }
  footer input { flex: 1 1 auto; width: 0; min-width: 0; font: inherit; font-size: max(16px, 1em); padding: 12px 0; border: 0; border-radius: 0; outline: none; color: inherit;
                 background: transparent; -webkit-appearance: none; appearance: none; box-shadow: none; }
  footer input[disabled] { opacity: .7; }
  footer .send { width: 36px; height: 36px; flex: 0 0 36px; border: 0; border-radius: 50%; background: var(--_accent); color: var(--_on-accent); display: grid; place-items: center; cursor: pointer;
                 transition: background .15s ease, color .15s ease; }
  footer .send svg, .field .mic svg { width: 18px; height: 18px; }
  footer .send[disabled] { background: transparent; color: var(--_muted); opacity: .55; cursor: default; }
  /* A layer over the conversation: the conversations kept, one read again, or "Call us". */
  .layer { position: absolute; inset: 0; z-index: 4; display: flex; flex-direction: column; background: var(--_surface); animation: k-in .18s cubic-bezier(.2,.8,.2,1); }
  .panel.layered footer { display: none; }
  .layer-bar { display: flex; align-items: center; gap: 4px; padding: 6px 10px 6px 6px; flex: 0 0 auto; border-bottom: 1px solid var(--_line); }
  .layer-bar h3 { flex: 1 1 auto; min-width: 0; margin: 0; font-size: 12px; font-weight: 500; letter-spacing: .14em; text-transform: uppercase;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .layer-bar .clear { border: 0; background: none; color: var(--_muted); font-size: 12.5px; cursor: pointer; padding: 6px 8px; }
  .layer-bar .clear:hover, .layer-bar .tool.forget:hover { color: var(--_failed); }
  .layer-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; display: flex; flex-direction: column; gap: 14px; padding: 14px 16px 16px; }
  .layer .lines { flex: 0 0 auto; padding: 0; overflow: visible; }
  .layer .status { padding: 0; }
  .kept { display: flex; flex-direction: column; }
  .kept-row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 11px 2px; border: 0; border-bottom: 1px solid var(--_line); background: none; color: inherit;
              text-align: left; cursor: pointer; }
  .kept-row:hover .kept-text { text-decoration: underline; text-underline-offset: 2px; }
  .kept-row i { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; display: grid; place-items: center; background: var(--_raised); color: var(--_muted); }
  .kept-row i svg { width: 16px; height: 16px; }
  .kept-words { flex: 1 1 auto; min-width: 0; }
  .kept-text { display: block; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kept-when { display: block; font-size: 12px; color: var(--_muted); }
  .layer .pill { flex: 0 0 auto; width: 100%; }
  /* "Call us": the number, the code to key, and the call's own lines once it is on. */
  .dial { display: flex; flex-direction: column; gap: 16px; }
  .step { display: grid; grid-template-columns: 24px 1fr; gap: 6px 12px; align-items: start; }
  .step .n { grid-row: span 2; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 500; background: var(--_accent); color: var(--_on-accent); }
  .step .say { font-size: 14px; font-weight: 500; line-height: 24px; }
  .step .say small { font-weight: 400; color: var(--_muted); font-size: 12.5px; }
  .number { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 10px 10px 16px; border-radius: 16px; background: var(--_raised); }
  .number b { font-size: 19px; font-weight: 500; letter-spacing: .02em; font-variant-numeric: tabular-nums; }
  .number a { display: inline-flex; align-items: center; gap: 6px; height: 40px; padding: 0 16px; border-radius: 999px; background: var(--_accent); color: var(--_on-accent);
              text-decoration: none; font-size: 14px; font-weight: 500; }
  .number a svg { width: 16px; height: 16px; }
  .digits { display: flex; gap: 8px; }
  .digits span { width: 48px; height: 56px; display: grid; place-items: center; font-size: 26px; font-weight: 500; font-variant-numeric: tabular-nums;
                 border: 1px solid var(--_line); border-radius: 12px; background: var(--_surface); }
  .waiting { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .waiting .status:not(.failed)::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--_accent); animation: pc-pulse 1.4s ease-in-out infinite; }
  .expires { font-size: 12px; color: var(--_muted); padding: 3px 10px; border-radius: 999px; background: var(--_raised); font-variant-numeric: tabular-nums; }
  .soon { padding: 18px; text-align: center; font-size: 13px; color: var(--_muted); border: 1px dashed var(--_line); border-radius: 16px; }
  .tools { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--_muted); cursor: pointer; user-select: none; white-space: nowrap; }
  .tools input { accent-color: var(--_accent); }
  @keyframes pc-pulse { 0%, 100% { opacity: .35; transform: scale(.85); } 50% { opacity: 1; transform: scale(1); } }
  .panel.maxed .lines { padding: 20px max(16px, calc(50% - 380px)); gap: 14px; }
  .panel.maxed footer { padding: 12px max(12px, calc(50% - 380px)); }
  .panel.maxed .lines li { font-size: 15.5px; }
  .panel.maxed .layer-body { padding: 20px max(16px, calc(50% - 380px)); }
  .panel.maxed .layer .lines { padding: 0; }
  @media ${PHONE} {
    .panel, .panel.sized, .panel.maxed { top: var(--_vv-top, 0px) !important; left: 0 !important; right: 0 !important; bottom: auto !important; width: auto !important;
      height: 100vh !important; height: var(--_vv-h, 100dvh) !important; border-radius: 0; }
    .edge, header .maximize { display: none !important; }
    footer { padding-bottom: max(10px, env(safe-area-inset-bottom)); }
  }
  @media (prefers-reduced-motion: reduce) { .panel, .layer { animation: none; } .waiting .status::before { animation: none; } }
`;
