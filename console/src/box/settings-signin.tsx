/** Sign-in: whether a stranger may sign up, the bot check on that door, and "Continue with Google" for everyone on the deployment. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { discovered } from "@pinecall/core/the-floor";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { Copy, useMove } from "../numbers/parts";
import { Field } from "../ui/setting";
import { readSignIn, removeGoogle, saveGoogle, type SignIn } from "./settings-door";
import { Effect, NoSuchDoor, Refusal, Section, useDoor } from "./settings-parts";

function GooglePanel({ was, onKept, onClose }: { was: SignIn["google"]; onKept: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const acting = useMove();
  const [clientId, setClientId] = useState(was.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [missing, setMissing] = useState(false);
  const save = (): void => {
    if (clientId.trim() === "" || secret.trim() === "") return setMissing(true);
    setMissing(false);
    void acting.move(async () => (await saveGoogle(credentials, { client_id: clientId.trim(), client_secret: secret.trim() }), await onKept())).then(onClose, () => undefined);
  };
  return (
    <EditDialog title="Continue with Google" icon="personas" about="One Google client for the whole deployment. No organization sets anything up." saving={acting.busy} refused={missing ? "Type both the client ID and its secret." : acting.refused} onSave={save} onClose={onClose}>
      <Effect>The Google button shows on every sign-in page. It signs in people who are already members: it never adds anyone to an organization.</Effect>
      <Field label="Client ID">
        <input className="cfg-input" aria-label="Client ID" placeholder="…apps.googleusercontent.com" spellCheck={false} autoComplete="off" value={clientId} onChange={(event) => setClientId(event.target.value)} />
      </Field>
      <Field label="Client secret">
        <input className="cfg-input" type="password" aria-label="Client secret" placeholder="Kept encrypted, never shown again" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} />
      </Field>
      <p className="dash-quiet">Make it at Google Cloud Console, under APIs &amp; Services, Credentials, OAuth client ID, Web application. Register the redirect address shown on this page there.</p>
    </EditDialog>
  );
}

export function SettingsSignIn(): ReactNode {
  const credentials = useCredentials();
  const signin = useDoor(useCallback(() => readSignIn(credentials), [credentials]));
  const open = useDoor(useCallback(() => discovered(credentials.base), [credentials.base]));
  const acting = useMove();
  const [editing, setEditing] = useState(false);
  const close = useCallback(() => setEditing(false), []);
  const google = signin.value?.google;
  const turnOff = (): void => void acting.move(async () => (await removeGoogle(credentials), await signin.reread())).catch(() => undefined);

  return (
    <>
      <Refusal>{signin.refused ?? acting.refused}</Refusal>

      <Section icon="personas" title="Sign-up" about="Whether someone nobody invited may create an organization here.">
        {open.value === undefined ? (
          <p className="dash-quiet tst-none">Reading…</p>
        ) : (
          <div className="tst-row bxs-row">
            <span className="tst-row-words">
              <span className="tst-row-name">{open.value.signup ? "Anyone may sign up" : "By invitation only"}</span>
              <span className="tst-row-under">{open.value.signup ? "A new person makes their own organization, and it gets what Admission says." : "People get in when an organization, or you, invites them."}</span>
            </span>
            <span className={`tst-status bxs-status tst-status-${open.value.signup ? "held" : "none"}`}>{open.value.signup ? "Open" : "Closed"}</span>
          </div>
        )}
        <p className="dash-quiet tst-none">This is chosen where the deployment is installed (PINECALL_SIGNUP), not on this page.</p>
      </Section>

      <Section
        icon="leave"
        title="Continue with Google"
        about="One button on the sign-in page, for the people of every organization."
        action={
          google !== undefined && (
            <button type="button" className="cfg-save tst-action" onClick={() => setEditing(true)}>
              {google.configured ? "Replace" : "Set up"}
            </button>
          )
        }
      >
        {signin.value === undefined && signin.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {signin.value === null && <NoSuchDoor />}
        {google !== undefined && !google.configured && <p className="dash-quiet tst-none">Off. People sign in with their email and password.</p>}
        {google?.configured === true && (
          <div className="tst-row bxs-row">
            <span className="tst-row-words">
              <span className="tst-row-name">Google sign-in</span>
              <span className="tst-row-under dash-clip">Client {google.client_id ?? "—"}. Its secret is kept and never shown.</span>
            </span>
            <span className="tst-status bxs-status tst-status-held">On</span>
            <ConfirmButton label="Turn off" asks="Remove the button for everyone?" danger onConfirm={turnOff} />
          </div>
        )}
        {google?.redirect_uri != null && (
          <div className="tst-row bxs-row">
            <span className="tst-row-words">
              <span className="tst-row-name">Redirect address</span>
              <span className="tst-row-under">Register it at Google as the authorized redirect URI, or Google refuses the sign-in.</span>
            </span>
            <Copy text={google.redirect_uri} />
          </div>
        )}
      </Section>

      <Section icon="privacy" title="Bot check" about="A Cloudflare Turnstile check on the doors a stranger knocks at: signing up, and a forgotten password.">
        {open.value === undefined ? (
          <p className="dash-quiet tst-none">Reading…</p>
        ) : (
          <div className="tst-row bxs-row">
            <span className="tst-row-words">
              <span className="tst-row-name">Cloudflare Turnstile</span>
              <span className="tst-row-under">{open.value.turnstile != null && open.value.turnstile !== "" ? "A sign-up or a password reset that does not pass it is refused. Signing in with a password never asks for it." : "Nothing stands between a script and the sign-up form."}</span>
            </span>
            <span className={`tst-status bxs-status tst-status-${open.value.turnstile != null && open.value.turnstile !== "" ? "held" : "none"}`}>{open.value.turnstile != null && open.value.turnstile !== "" ? "On" : "Off"}</span>
          </div>
        )}
        <p className="dash-quiet tst-none">Its two keys are set where the deployment is installed (PINECALL_TURNSTILE_SITE_KEY and PINECALL_TURNSTILE_SECRET), not on this page.</p>
      </Section>

      {editing && google !== undefined && <GooglePanel was={google} onKept={signin.reread} onClose={close} />}
    </>
  );
}
