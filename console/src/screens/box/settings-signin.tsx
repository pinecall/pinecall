/** Box-wide "Continue with Google" settings. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { googleCallback } from "@pinecall/core/login";
import { theBoxsOwnName } from "../../lib/mode";
import { Button, Card, CardHead, Field, Input, KV, Pill, Refused, TextAction } from "../../ui";
import { readSignIn, removeGoogle, saveGoogle } from "./door-settings";
import { NoSuchDoor } from "./settings";
import { useDoor, useMove } from "./use-door";

/**
 * One OAuth client for the whole box. A verified address signs in only if it is already a member
 * of some org; signing in never creates a membership.
 */
export function SettingsSignIn(): ReactNode {
  const credentials = useCredentials();
  const signin = useDoor(useCallback(() => readSignIn(credentials), [credentials]));
  const acting = useMove();
  const [editing, setEditing] = useState(false);
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [copied, setCopied] = useState(false);

  if (signin.value === undefined) return <Refused>{signin.refused}</Refused>;
  if (signin.value === null) return <NoSuchDoor />;

  const google = signin.value.google;
  const redirect = google.redirect_uri ?? googleCallback(theBoxsOwnName());
  const form = editing || !google.configured;

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const kept = await acting.move(async () => {
      await saveGoogle(credentials, { client_id: clientId.trim(), client_secret: secret.trim() });
      await signin.reread();
    });
    if (kept) {
      setSecret("");
      setEditing(false);
    }
  };

  return (
    <>
      <Refused>{acting.refused}</Refused>
      <Card>
        <CardHead title="Continue with Google" meta="one client for the whole box — no org configures anything">
          <span className="box-head-moves">
            <Pill tone={google.configured ? "green" : "gray"}>{google.configured ? "on" : "off"}</Pill>
          </span>
        </CardHead>

        {form ? (
          <form className="box-form" onSubmit={(event) => void save(event)}>
            <div className="box-form-grid">
              <Field label="Client ID">
                <Input value={clientId} placeholder="…apps.googleusercontent.com" onChange={(event) => setClientId(event.target.value)} required />
              </Field>
              <Field label="Client secret, sent once">
                <Input type="password" autoComplete="off" value={secret} placeholder="never shown again" onChange={(event) => setSecret(event.target.value)} required />
              </Field>
            </div>
            <div className="box-line">
              <Button kind="primary" size="md" type="submit" disabled={acting.busy}>
                {acting.busy ? "Saving…" : "Save"}
              </Button>
              {editing && <TextAction onClick={() => setEditing(false)}>Cancel</TextAction>}
              <span className="ui-note">Made at Google Cloud Console → APIs &amp; Services → Credentials → OAuth client ID → Web application.</span>
            </div>
          </form>
        ) : (
          <div className="box-kvs">
            <KV label="Client ID" keyWidth={120}>
              <span className="box-fixed">{google.client_id ?? "—"}</span>
            </KV>
            <KV label="Secret" keyWidth={120}>
              kept, and read back by no door
            </KV>
            <div className="box-line box-kvs-moves">
              <Button size="sm" onClick={() => { setClientId(google.client_id ?? ""); setEditing(true); }}>
                Change
              </Button>
              <TextAction
                danger
                disabled={acting.busy}
                onClick={() =>
                  void acting.move(async () => {
                    await removeGoogle(credentials);
                    await signin.reread();
                  })
                }
              >
                Turn it off
              </TextAction>
            </div>
          </div>
        )}

        <div className="box-redirect">
          <div className="box-redirect-head">
            <span className="ui-note">Register this at Google as the authorized redirect URI</span>
            <Button size="xs" onClick={() => void navigator.clipboard.writeText(redirect).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="ui-code">{redirect}</pre>
        </div>
      </Card>
    </>
  );
}
