/** Terminal screen: approve a pending `pinecall login`. */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button } from "../../ui";
import { approve, asking, type Asked } from "./door";
import "./terminal.css";

// The code is a query parameter; `pinecall login` builds the same URL (cli/login.ts, `signingIn`).
const WORD = "c";

// Fallback when the CLI sent no hostname.
const A_TERMINAL = "a terminal";

/**
 * Passwords are typed in the browser (autofill, password managers), never in a shell history.
 * Approving mints the terminal its own revocable key, which never passes through this page.
 */
export function Terminal(): ReactNode {
  const credentials = useCredentials();
  const [params] = useSearchParams();
  const code = params.get(WORD);
  const [asked, setAsked] = useState<Asked | null>(null);
  const [busy, setBusy] = useState(false);
  const [signed, setSigned] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    if (code === null) return;
    let gone = false;
    asking(credentials, code).then(
      (found) => {
        if (!gone) setAsked(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, code]);

  const sign = async (): Promise<void> => {
    if (code === null) return;
    setBusy(true);
    setRefused(null);
    try {
      setSigned(await approve(credentials, code));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  if (code === null) return <Card title="No terminal is asking" lede={NOTHING_ASKED} />;
  if (signed !== null) {
    return <Card title="Your terminal is signed in" lede={`Go back to it. You are in ${signed}.`} />;
  }
  if (refused !== null && asked === null) return <Card title="That link is no good" lede={refused} />;

  return (
    <Card
      title="Sign this terminal in?"
      lede={`A terminal calling itself ${asked?.device ?? A_TERMINAL} asked to be signed in as you. Approve it only if you just ran "pinecall login" on that machine yourself.`}
    >
      <Button kind="primary" size="lg" onClick={() => void sign()} disabled={busy || asked === null}>
        {busy ? "Signing in…" : "Yes, that is my terminal"}
      </Button>
      {refused !== null && <p className="terminal-refused">{refused}</p>}
    </Card>
  );
}

// No code in the URL: /cli opened by hand or a truncated link.
const NOTHING_ASKED = "Run `pinecall login` in your terminal — it prints a link, and that link comes back here.";

/** Centred panel for each state of the screen. */
function Card({ title, lede, children }: { title: string; lede: string; children?: ReactNode }): ReactNode {
  return (
    <div className="terminal">
      <div className="terminal-card">
        <img className="terminal-mark" src="/pinecall-mark.png" alt="" />
        <h1 className="terminal-title">{title}</h1>
        <p className="terminal-lede">{lede}</p>
        {children}
      </div>
    </div>
  );
}
