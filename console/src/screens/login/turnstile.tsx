/** Cloudflare Turnstile, drawn where the gateway names a site key: the token it yields rides the next keyless request. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

// Each door sends its own action, and the gateway holds Cloudflare's answer to it (accounts/service/turnstile.py).
export type Action = "login" | "signup" | "signup_resend" | "password_reset";

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(
    container: HTMLElement,
    options: {
      sitekey: string;
      action: Action;
      theme: "dark";
      callback: (token: string) => void;
      "expired-callback": () => void;
      "error-callback": () => void;
    },
  ): string;
  remove(id: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

/** Cloudflare's script, fetched once per page and only where a widget is drawn. */
function loaded(): Promise<TurnstileApi> {
  if (window.turnstile !== undefined) return Promise.resolve(window.turnstile);
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () => (window.turnstile === undefined ? reject(new Error("Turnstile did not load")) : resolve(window.turnstile));
    script.onerror = () => reject(new Error("Turnstile did not load"));
    document.head.append(script);
  });
  return loading;
}

/** The widget for one door; a new mount is a new token, since a token is one use. */
function Widget({ siteKey, action, onToken }: { siteKey: string; action: Action; onToken: (token: string | null) => void }): ReactNode {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let gone = false;
    let id: string | undefined;
    loaded()
      .then((api) => {
        if (gone || box.current === null) return;
        id = api.render(box.current, {
          sitekey: siteKey,
          action,
          theme: "dark",
          callback: onToken,
          "expired-callback": () => onToken(null),
          "error-callback": () => onToken(null),
        });
      })
      .catch(() => onToken(null));
    return () => {
      gone = true;
      if (id !== undefined) window.turnstile?.remove(id);
    };
  }, [siteKey, action, onToken]);
  return <div ref={box} className="login-turnstile" />;
}

export interface Captcha {
  /** Whether this gateway asks for a token at all. */
  required: boolean;
  /** Whether the next request may go: no token asked for, or one in hand. */
  ready: boolean;
  /** The widget to draw above the button, or nothing where the gateway asks for none. */
  widget: ReactNode;
  /** The token for one request, and the widget starts over for the next. */
  spend: () => string | null;
}

/** A door's captcha: nothing where the floor names no site key, else the widget and its one-use token. */
export function useTurnstile(siteKey: string | null | undefined, action: Action): Captcha {
  const required = typeof siteKey === "string" && siteKey !== "";
  const [token, setToken] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  const spend = useCallback((): string | null => {
    setToken(null);
    setRound((n) => n + 1);
    return token;
  }, [token]);
  return {
    required,
    ready: !required || token !== null,
    widget: required ? <Widget key={round} siteKey={siteKey} action={action} onToken={setToken} /> : null,
    spend,
  };
}
