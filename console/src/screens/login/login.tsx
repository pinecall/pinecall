/** Login screen: email, password and workspace choice, yielding a key for this tab. */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { discovered, type Discovered } from "@pinecall/core/the-floor";
import { loginWithPassword, orgsForPassword, ssoOrgsFor, ssoUrl, type Opens, type Signed, type SsoOrg } from "@pinecall/core/login";
import { DEVICE } from "../../lib/device";
import { inTheWorld, WORLD } from "../../lib/mode";
import { ContinueWithGoogle } from "./google-button";
import { WayIn } from "./way-in";

/**
 * One login for both worlds. Google and a sign-up are offered only where the gateway says it has
 * them (`/.well-known/pinecall`): the console ships in every self-hosted runtime. An org's own
 * provider is never a button: it shows once the address typed is of a domain an org proved.
 * The gateway returns one refusal for every failure so it doesn't reveal which orgs exist.
 */
export function Login({ base, onSigned }: { base: string; onSigned: (signed: Signed) => void }): ReactNode {
  const [org, setOrg] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  // Google and an org's provider return refusals in the query string.
  const [refused, setRefused] = useState<string | null>(() => new URLSearchParams(window.location.search).get("refused"));
  const [forgot, setForgot] = useState(false);
  const [floor, setFloor] = useState<Discovered | null>(null);
  // Asked on password blur, not per keystroke: the door shares the login throttle.
  const [opens, setOpens] = useState<Opens[] | null>(null);
  const [known, setKnown] = useState(true);
  const asked = useRef("");
  const [ssoOrgs, setSsoOrgs] = useState<SsoOrg[] | null>(null);
  const ssoAsked = useRef("");

  useEffect(() => {
    let gone = false;
    // Google and a sign-up are shown only when the gateway advertises them.
    void discovered(base).then((said) => {
      if (!gone) setFloor(said);
    });
    return () => {
      gone = true;
    };
  }, [base]);

  // Asked on the address's blur, once per address: the door shares the login throttle.
  const askSso = async (): Promise<void> => {
    const typed = email.trim().toLowerCase();
    if (!typed.includes("@") || typed === ssoAsked.current) return;
    ssoAsked.current = typed;
    try {
      setSsoOrgs(await ssoOrgsFor(base, typed));
    } catch {
      // An older gateway without the door, or the throttle: the password still works.
      setSsoOrgs(null);
    }
  };

  const askOrgs = async (): Promise<void> => {
    const pair = `${email.trim()}\n${password}`;
    if (email.trim() === "" || password === "" || pair === asked.current) return;
    asked.current = pair;
    try {
      const listed = await orgsForPassword(base, email.trim(), password);
      if (listed === null) {
        setKnown(false);
        return;
      }
      setOpens(listed);
      const first = listed[0];
      if (listed.length > 0 && !listed.some((one) => (one.slug ?? one.org) === org) && first !== undefined) setOrg(first.slug ?? first.org);
    } catch {
      // Wrong password: the refusal is shown on submit.
      setOpens(null);
    }
  };

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      onSigned(await loginWithPassword(base, { org: org.trim(), email: email.trim(), password }, DEVICE));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  const hasGoogle = floor?.google === true;
  return (
    <WayIn
      title="Sign in"
      lede={hasGoogle ? "Continue with Google, or with your email and password." : "Use the email and password you were invited with."}
      aside={
        floor?.signup === true ? (
          <>
            New here? <a href={inTheWorld(WORLD, "/signup")}>Create an account</a>
          </>
        ) : undefined
      }
    >
      <form onSubmit={(event) => void submit(event)}>
        {hasGoogle && <ContinueWithGoogle base={base} />}

        <label className="login-label" htmlFor="login-email">
          Email
        </label>
        <input
          id="login-email"
          className="login-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          onBlur={() => void askSso()}
          autoComplete="username"
          autoFocus={!hasGoogle}
          required
        />
        {ssoOrgs !== null && ssoOrgs.length > 0 && (
          <div className="login-sso-pick">
            {ssoOrgs.map((one) => (
              <button key={one.org} type="button" className="login-sso" onClick={() => window.location.assign(ssoUrl(base, one.slug ?? one.org))}>
                <span className="login-sso-glyph" />
                Continue with {one.name ?? one.slug ?? one.org}
              </button>
            ))}
            <p className="login-sso-note">Your workspace signs you in with its own provider.</p>
          </div>
        )}

        <div className="login-label-row">
          <label className="login-label" htmlFor="login-password">
            Password
          </label>
          <button type="button" className="login-link" onClick={() => setForgot(!forgot)}>
            Forgot password
          </button>
        </div>
        <input
          id="login-password"
          className="login-input login-input-secret"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onBlur={() => void askOrgs()}
          autoComplete="current-password"
          required
        />
        {forgot && (
          <p className="login-forgot">
            Ask an admin of your workspace: from Team they hand you a one-use link where you choose a new password.
          </p>
        )}

        {opens !== null && opens.length > 0 ? (
          <>
            <label className="login-label" htmlFor="login-org">
              Workspace
            </label>
            <div className="login-workspace">
              <span className="login-workspace-tile">{(org[0] ?? "·").toUpperCase()}</span>
              <select id="login-org" className="login-workspace-input" value={org} onChange={(event) => setOrg(event.target.value)} disabled={opens.length === 1}>
                {opens.map((one) => (
                  <option key={one.org} value={one.slug ?? one.org}>
                    {one.name ?? one.slug ?? one.org}
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : (
          !known && (
            <>
              <div className="login-label-row">
                <label className="login-label" htmlFor="login-org">
                  Workspace
                </label>
                <span className="login-hint">only if you belong to several</span>
              </div>
              <div className="login-workspace">
                <span className="login-workspace-tile">{(org.trim()[0] ?? "·").toUpperCase()}</span>
                <input
                  id="login-org"
                  className="login-workspace-input"
                  value={org}
                  onChange={(event) => setOrg(event.target.value)}
                  autoComplete="organization"
                  placeholder="the oldest of yours"
                />
              </div>
            </>
          )
        )}

        <button className="login-go" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        {refused !== null && <p className="login-refused">{refused}</p>}

        <p className="login-note">
          {hasGoogle
            ? "Invited and no password yet? Continue with Google on the address you were invited at, or open the link in your invitation."
            : "Invited and no password yet? Open the link in your invitation — that is where you choose one."}
        </p>
      </form>
    </WayIn>
  );
}
