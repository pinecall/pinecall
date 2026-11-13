/** `/cli`: approve a waiting `pinecall login`, the one way a terminal signs in. */

import { useEffect, useState, type ReactNode } from "react";
import { z } from "zod";

import { GatewayError, post, read, type Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WayIn } from "./way-in";
import "./login.css";

// The code is a query parameter; `pinecall login` builds the same address (cli/src/accounts/service/signin.ts).
const WORD = "c";
// When the CLI sent no hostname.
const A_TERMINAL = "a terminal";
// /cli opened by hand, or a link cut short.
const NOTHING_ASKED = "Run `pinecall login` in your terminal: it prints a link, and that link comes back here.";

// The minted key goes to the terminal through its own door; this page never sees it.
const AskedSchema = z.object({ device: z.string().nullable(), expires_at: z.number(), answered: z.boolean() });
const ApprovedSchema = z.object({ device: z.string().nullable(), org: z.string(), org_name: z.string() });
type Asked = z.infer<typeof AskedSchema>;

const at = (code: string): string => `/v1/login/pairings/${encodeURIComponent(code)}`;

/** The code read without being spent, so the tab can be reloaded. */
async function asking(credentials: Credentials, code: string): Promise<Asked> {
  return AskedSchema.parse(await read(credentials, at(code)));
}

/** The terminal approved as this person: a key of its own, labelled with its machine, collected once by the CLI. */
async function approve(credentials: Credentials, code: string): Promise<string> {
  return ApprovedSchema.parse(await post(credentials, at(code), {})).org_name;
}

const said = (failed: unknown): string => (failed instanceof GatewayError ? failed.message : String(failed));

// The console was started over on 2026-11-10 without this page: /cli fell through to the dashboard,
// and every `pinecall login` waited for an approval nobody could give.
/** Approve a pending terminal sign-in, once the person here is signed in themselves. */
export function Terminal(): ReactNode {
  const credentials = useCredentials();
  const code = new URLSearchParams(window.location.search).get(WORD);
  const [asked, setAsked] = useState<Asked | null>(null);
  const [busy, setBusy] = useState(false);
  const [signed, setSigned] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    if (code === null) return undefined;
    let gone = false;
    asking(credentials, code).then(
      (found) => !gone && setAsked(found),
      (failed: unknown) => !gone && setRefused(said(failed)),
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
      setRefused(said(failed));
    } finally {
      setBusy(false);
    }
  };

  if (code === null) return <WayIn title="No terminal is asking" lede={NOTHING_ASKED} />;
  if (signed !== null) return <WayIn title="Your terminal is signed in" lede={`Go back to it: you are in ${signed}.`} />;
  if (refused !== null && asked === null) return <WayIn title="That link is no good" lede={refused} />;
  if (asked?.answered === true) return <WayIn title="Already answered" lede="This terminal's sign-in was answered already. Go back to it, or run `pinecall login` again." />;
  return (
    <WayIn
      title="Sign this terminal in?"
      lede={`A terminal calling itself ${asked?.device ?? A_TERMINAL} asked to be signed in as you. Approve it only if you just ran "pinecall login" on that machine yourself.`}
    >
      <button className="login-go" type="button" onClick={() => void sign()} disabled={busy || asked === null}>
        {busy ? "Signing in…" : "Yes, that is my terminal"}
      </button>
      {refused !== null && <p className="login-refused">{refused}</p>}
    </WayIn>
  );
}
