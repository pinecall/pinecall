/** Somebody Google vouched for whom nobody knows: one field, the workspace's name, and the org is made. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { type Signed } from "@pinecall/core/login";
import { googleNewcomer, signUpWithGoogle, type GoogleNewcomer } from "@pinecall/core/signup";
import { DEVICE } from "../lib/key";
import { WORLD_BASE } from "../lib/world";
import { ContinueWithGoogle } from "./google-button";
import { WayIn } from "./way-in";

/** "Ana's workspace" for Ana Pérez: a name to keep or to type over, never one the page insists on. */
function aWorkspaceFor(person: string): string {
  const first = person.trim().split(/\s+/)[0] ?? "";
  return first === "" ? "" : `${first}'s workspace`;
}

/**
 * The token rides `?google=` until the org is made, so a reload keeps the page; it is spent once,
 * and lives ten minutes. `onMade` keeps the key and carries the person on.
 */
export function NamedByGoogle({ base, token, onMade }: { base: string; token: string; onMade: (signed: Signed) => void }): ReactNode {
  const [newcomer, setNewcomer] = useState<GoogleNewcomer | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let left = false;
    googleNewcomer(base, token).then(
      (found) => {
        if (left) return;
        setNewcomer(found);
        setName(aWorkspaceFor(found.person));
      },
      (failed: unknown) => {
        if (!left) setGone(failed instanceof GatewayError ? failed.message : String(failed));
      },
    );
    return () => {
      left = true;
    };
  }, [base, token]);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      onMade(await signUpWithGoogle(base, token, name.trim(), DEVICE));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setBusy(false);
    }
  };

  if (gone !== null) {
    return (
      <WayIn title="That sign-in is over" lede={gone}>
        <ContinueWithGoogle base={base} />
        <a className="login-link" href={WORLD_BASE}>
          Sign in with your email instead
        </a>
      </WayIn>
    );
  }
  if (newcomer === null) return <WayIn title="Name your workspace" />;
  return (
    <WayIn
      title="Name your workspace"
      lede={
        <>
          You're signed in with Google as <b>{newcomer.email}</b>. One name and you're in — you can change it later.
        </>
      }
    >
      <form onSubmit={(event) => void submit(event)}>
        <label className="login-label" htmlFor="google-workspace">
          Workspace
        </label>
        <input
          id="google-workspace"
          className="login-input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="organization"
          maxLength={120}
          autoFocus
          required
        />
        <button className="login-go" type="submit" disabled={busy || name.trim() === ""}>
          {busy ? "Creating your workspace…" : "Create workspace"}
        </button>
        {refused !== null && <p className="login-refused">{refused}</p>}
      </form>
    </WayIn>
  );
}
