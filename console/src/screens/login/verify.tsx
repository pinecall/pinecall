/** The mailed code back: six digits, and the org is made with a key of this tab's own in it. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { resendSignUpCode, verifySignUp } from "@pinecall/core/signup";
import { discovered } from "@pinecall/core/the-floor";
import { type Signed } from "@pinecall/core/login";
import { DEVICE } from "../../lib/device";
import { inTheWorld, WORLD } from "../../lib/mode";
import { useTurnstile } from "./turnstile";
import { WayIn } from "./way-in";

const RESEND_WAIT_S = 30;
const SIX_DIGITS = /^\d{6}$/;

export function Verify({ base, onSigned }: { base: string; onSigned: (signed: Signed) => void }): ReactNode {
  const email = new URLSearchParams(window.location.search).get("email") ?? "";
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [resent, setResent] = useState(false);
  const [siteKey, setSiteKey] = useState<string | null>(null);
  // A resend mails a letter, so it is a door with a captcha where the gateway has one.
  const captcha = useTurnstile(siteKey, "signup_resend");
  const startOver = inTheWorld(WORLD, "/signup");

  useEffect(() => {
    let gone = false;
    void discovered(base).then((said) => {
      if (!gone) setSiteKey(said.turnstile ?? null);
    });
    return () => {
      gone = true;
    };
  }, [base]);

  useEffect(() => {
    if (wait <= 0) return;
    const tick = window.setTimeout(() => setWait(wait - 1), 1000);
    return () => window.clearTimeout(tick);
  }, [wait]);

  if (email === "") {
    return (
      <WayIn
        title="Nothing to confirm here"
        aside={
          <>
            <a href={startOver}>Start over</a>
          </>
        }
      />
    );
  }

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!SIX_DIGITS.test(code)) {
      setRefused("The code is six digits.");
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      onSigned(await verifySignUp(base, email, code, DEVICE));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setBusy(false);
    }
  };

  const resend = async (): Promise<void> => {
    if (wait > 0 || !captcha.ready) return;
    setWait(RESEND_WAIT_S);
    setResent(false);
    try {
      await resendSignUpCode(base, email, captcha.spend());
      setResent(true);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  return (
    <WayIn
      title="Check your inbox"
      lede={
        <>
          We sent a six-digit code to <b>{email}</b>. It works for fifteen minutes.
        </>
      }
      aside={
        <>
          Wrong email? <a href={startOver}>Start over</a>
        </>
      }
    >
      <form onSubmit={(event) => void submit(event)}>
        <label className="login-label" htmlFor="verify-code">
          Code
        </label>
        <input
          id="verify-code"
          className="login-input login-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          autoFocus
        />

        <button className="login-go" type="submit" disabled={busy || code.length !== 6}>
          {busy ? "Checking…" : "Open my sandbox"}
        </button>

        {refused !== null && <p className="login-refused">{refused}</p>}

        {captcha.widget}

        <p className="login-note">
          No code?{" "}
          <button type="button" className="login-resend" onClick={() => void resend()} disabled={wait > 0 || !captcha.ready}>
            {wait > 0 ? `Send another in ${wait}s` : "Send another"}
          </button>
          {resent && wait > 0 && " Sent."}
        </p>
      </form>
    </WayIn>
  );
}
