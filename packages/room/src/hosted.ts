/** A page Pinecall serves for an app: its tickets, its codes and its dictations asked of the page's own name, the captcha solved first. */

import type { Code, Minted } from "./server/index.js";

/** What `room()` is given on a page deployed with its app: `room({ ...hosted() })`. */
export interface Hosted {
  tokens: (scope: "talk" | "chat", resume?: string) => Promise<Minted>;
  expect: () => Promise<Code>;
  /** One dictation into a field of the page, in a language: what `<pinecall-widget>` takes as its `dictationProvider`. */
  dictation: (language?: string) => Promise<Dictating>;
}

/** What one dictation is opened with: the gateway's socket, a minute long, and the words to write the page's own way. */
export interface Dictating {
  url: string;
  hear: string[];
}

export interface HostedOptions {
  /** Where the page's routes are, when not at the page's own origin: a dev server that proxies them. */
  at?: string | undefined;
  fetch?: typeof fetch | undefined;
}

/** What `GET /pinecall/config` answers: the agent a visitor reaches, and the captcha's site key where one is asked. */
interface PageConfig {
  agent: string;
  turnstile: string | null;
}

/** The part of Cloudflare's Turnstile this file uses. */
interface Turnstile {
  render(into: HTMLElement, options: Record<string, unknown>): string;
  remove(widget: string): void;
}

const TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
// The action the gateway asks the token to have been solved for.
const ACTION = "page";
const NO_CAPTCHA = "the captcha could not be loaded: check the connection, or a blocker, and try again";
// Cloudflare's codes for a widget asked for on a name it was not made for (110200) or with a key it does not know (1101xx).
const NOT_THIS_NAME = /^1102/;
const NOT_THIS_KEY = /^1101/;

/** What Cloudflare's error code means for whoever runs the page; the code itself for one this file does not know. */
function refusalOf(code: unknown): string {
  const said = typeof code === "string" || typeof code === "number" ? String(code) : "";
  if (NOT_THIS_NAME.test(said)) return `the captcha is not set up for ${location.hostname}: add this name to the Turnstile widget's hostnames (Cloudflare ${said})`;
  if (NOT_THIS_KEY.test(said)) return `the captcha's site key is not one Cloudflare knows (Cloudflare ${said})`;
  return said === "" ? NO_CAPTCHA : `the captcha failed (Cloudflare ${said}): try again`;
}

/**
 * The page's side of an app's own page: the ticket and the code are asked of `/pinecall/token` and
 * `/pinecall/code`, which Pinecall answers for a deployed app and `pinecall start` answers on this
 * machine. Where the gateway asks for a captcha it is solved first, shown only when Cloudflare asks
 * the visitor for something.
 */
export function hosted(options: HostedOptions = {}): Hosted {
  const at = (options.at ?? "").replace(/\/+$/, "");
  const ask = options.fetch ?? fetch;
  let config: Promise<PageConfig> | null = null;

  const configured = (): Promise<PageConfig> => {
    config ??= ask(`${at}/pinecall/config`).then(async (answer) => {
      const body: unknown = await answer.json();
      if (!answer.ok || !isConfig(body)) throw new Error(detailOf(body) ?? `the page's config answered ${answer.status}`);
      return body;
    });
    // A config that failed is asked for again by the next ticket.
    config.catch(() => (config = null));
    return config;
  };

  const asked = async (path: string, said: Record<string, unknown>): Promise<unknown> => {
    const { turnstile } = await configured();
    const body = turnstile === null ? said : { ...said, turnstile: await solved(turnstile) };
    const answer = await ask(`${at}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const answered: unknown = await answer.json().catch(() => null);
    if (!answer.ok) throw new Error(detailOf(answered) ?? `the page's server answered ${answer.status}`);
    return answered;
  };

  return {
    async tokens(scope, resume) {
      const minted = await asked("/pinecall/token", resume === undefined ? { scope } : { scope, resume });
      if (!hasStrings(minted, ["server_url", "participant_token", "call", "log_token"])) throw new Error("the page's server answered a ticket this package does not know");
      return minted;
    },
    async dictation(language) {
      const minted = await asked("/pinecall/dictation", language === undefined ? {} : { language });
      if (!hasStrings(minted, ["url"])) throw new Error("the page's server answered a dictation this package does not know");
      const hear: unknown = Reflect.get(minted, "hear");
      return { url: minted.url, hear: Array.isArray(hear) ? hear.filter((word): word is string => typeof word === "string") : [] };
    },
    async expect() {
      const code = await asked("/pinecall/code", {});
      const expires: unknown = typeof code === "object" && code !== null ? Reflect.get(code, "expires_at") : null;
      if (!hasStrings(code, ["code", "number", "code_token"]) || typeof expires !== "number") throw new Error("the page's server answered a code this package does not know");
      return { code: code.code, number: code.number, code_token: code.code_token, expires_at: expires };
    },
  };
}

// One token per ticket: Cloudflare's are spent when the gateway verifies them.
async function solved(sitekey: string): Promise<string> {
  const turnstile = await loaded();
  const holder = document.createElement("div");
  holder.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647";
  document.body.append(holder);
  let widget = "";
  try {
    return await new Promise<string>((solve, refuse) => {
      widget = turnstile.render(holder, {
        sitekey,
        action: ACTION,
        appearance: "interaction-only",
        callback: (token: string) => solve(token),
        "error-callback": (code: unknown) => {
          refuse(new Error(refusalOf(code)));
          // Told Cloudflare the error is handled: it logs nothing more and does not retry on its own.
          return true;
        },
      });
    });
  } finally {
    if (widget !== "") turnstile.remove(widget);
    holder.remove();
  }
}

function loaded(): Promise<Turnstile> {
  const here = turnstileOf();
  if (here !== null) return Promise.resolve(here);
  return new Promise<Turnstile>((ready, refused) => {
    const script = document.createElement("script");
    script.src = TURNSTILE;
    script.async = true;
    script.onload = () => {
      const now = turnstileOf();
      if (now === null) refused(new Error(NO_CAPTCHA));
      else ready(now);
    };
    script.onerror = () => refused(new Error(NO_CAPTCHA));
    document.head.append(script);
  });
}

function turnstileOf(): Turnstile | null {
  const found: unknown = Reflect.get(globalThis, "turnstile");
  return isTurnstile(found) ? found : null;
}

function isTurnstile(found: unknown): found is Turnstile {
  return typeof found === "object" && found !== null && typeof Reflect.get(found, "render") === "function" && typeof Reflect.get(found, "remove") === "function";
}

function isConfig(body: unknown): body is PageConfig {
  if (typeof body !== "object" || body === null) return false;
  const turnstile: unknown = Reflect.get(body, "turnstile");
  return typeof Reflect.get(body, "agent") === "string" && (turnstile === null || typeof turnstile === "string");
}

function detailOf(body: unknown): string | null {
  const detail: unknown = typeof body === "object" && body !== null ? Reflect.get(body, "detail") : null;
  return typeof detail === "string" ? detail : null;
}

function hasStrings<F extends string>(body: unknown, fields: readonly F[]): body is Record<F, string> & Record<string, unknown> {
  return typeof body === "object" && body !== null && fields.every((field) => typeof Reflect.get(body, field) === "string");
}
