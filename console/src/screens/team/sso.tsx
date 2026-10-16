/** Single sign-on: the identity provider this org's people prove who they are with. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, KV, Refused, Select, SelectItem, Switch } from "../../ui";
import { readSso, removeSso, ROLES, saveSso, type Member, type Sso } from "./door";

// Nobody arrives new: a person the provider vouches for still has to be invited first.
const NOBODY = "";

/**
 * The card. Drawn only when the gateway has the door; a gateway with no vault answers 503 and its
 * sentence is shown in the card's place. The secret is typed once and never read back.
 */
export function SingleSignOn(): ReactNode {
  const credentials = useCredentials();
  const [sso, setSso] = useState<Sso | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [sure, setSure] = useState(false);

  useEffect(() => {
    let gone = false;
    readSso(credentials).then(
      (found) => {
        if (!gone) setSso(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  if (sso === null) {
    return refused === null ? null : (
      <Card>
        <CardHead title="Single sign-on" />
        <div className="ui-card-body">
          <Refused>{refused}</Refused>
        </div>
      </Card>
    );
  }

  const remove = async (): Promise<void> => {
    if (!sure) {
      setSure(true);
      return;
    }
    setRefused(null);
    try {
      await removeSso(credentials);
      setSso(await readSso(credentials));
      setSure(false);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Card>
      <CardHead
        title="Single sign-on"
        meta={sso.configured ? "this org's people sign in with its identity provider" : "sign in with Google Workspace, Okta or Entra instead of a password"}
      >
        {sso.configured && !editing && (
          <span className="team-link-moves">
            <Button size="xs" onClick={() => setEditing(true)}>
              Change
            </Button>
            <Button size="xs" kind="danger" onClick={() => void remove()} onBlur={() => setSure(false)}>
              {sure ? "Remove · sure?" : "Remove"}
            </Button>
          </span>
        )}
      </CardHead>

      {sso.configured && !editing ? (
        <div className="team-sso-values">
          <KV label="Issuer">{sso.issuer}</KV>
          <KV label="Client ID">{sso.client_id}</KV>
          <KV label="Client secret">kept, and never shown</KV>
          <KV label="Allowed domains">{sso.domains.join(", ") || "—"}</KV>
          <KV label="Arriving new">{sso.role ?? "nobody: invite first"}</KV>
          <KV label="Passwords">{sso.required ? "stopped for this org" : "still work beside it"}</KV>
        </div>
      ) : (
        <SsoForm
          sso={sso}
          onSaved={(saved) => {
            setSso(saved);
            setEditing(false);
          }}
          onCancel={sso.configured ? () => setEditing(false) : undefined}
        />
      )}

      <Redirect uri={sso.redirect_uri} />
      {refused !== null && (
        <div className="ui-card-body">
          <Refused>{refused}</Refused>
        </div>
      )}
    </Card>
  );
}

function SsoForm({ sso, onSaved, onCancel }: { sso: Sso; onSaved: (saved: Sso) => void; onCancel: (() => void) | undefined }): ReactNode {
  const credentials = useCredentials();
  const [issuer, setIssuer] = useState(sso.issuer ?? "");
  const [clientId, setClientId] = useState(sso.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [domains, setDomains] = useState(sso.domains.join(" "));
  const [role, setRole] = useState<string>(sso.role ?? NOBODY);
  const [required, setRequired] = useState(sso.required);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      onSaved(
        await saveSso(credentials, {
          issuer: issuer.trim(),
          client_id: clientId.trim(),
          client_secret: secret,
          domains: domains.split(/[\s,]+/).filter((one) => one !== ""),
          role: role === NOBODY ? null : (role as Member["role"]),
          required,
        }),
      );
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="team-sso-form" onSubmit={(event) => void submit(event)}>
      <div className="team-sso-grid">
        <Field label="Issuer URL">
          <Input type="url" placeholder="https://accounts.google.com" value={issuer} onChange={(event) => setIssuer(event.target.value)} required />
        </Field>
        <Field label="Client ID">
          <Input value={clientId} onChange={(event) => setClientId(event.target.value)} required />
        </Field>
        <Field label="Client secret, sent once">
          <Input type="password" autoComplete="off" placeholder="never shown again" value={secret} onChange={(event) => setSecret(event.target.value)} required />
        </Field>
        <Field label="Allowed domains">
          <Input placeholder="company.com other.com" value={domains} onChange={(event) => setDomains(event.target.value)} required />
        </Field>
        <Field label="Role for people who arrive new">
          <Select value={role} onValueChange={(value) => setRole(value)}>
            <SelectItem value={NOBODY}>nobody: invite first</SelectItem>
            {ROLES.map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </Select>
        </Field>
        <div className="team-sso-required">
          <span className="team-sso-required-words">Passwords stop working for this org</span>
          <Switch on={required} onChange={setRequired} label="Passwords stop working for this org" />
        </div>
      </div>
      <div className="team-sso-moves">
        <Button kind="primary" size="form" type="submit" disabled={busy}>
          {busy ? "Asking the issuer…" : "Save"}
        </Button>
        {onCancel !== undefined && (
          <Button size="form" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <span className="ui-note">The gateway asks the issuer for its discovery document before it keeps anything.</span>
      </div>
      <Refused>{refused}</Refused>
    </form>
  );
}

/** The one address the provider must be told about. */
function Redirect({ uri }: { uri: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  return (
    <div className="team-sso-redirect">
      <div className="team-sso-redirect-head">
        <span className="ui-note">Register this at your identity provider as the redirect URI</span>
        <Button
          size="xs"
          onClick={() => {
            void navigator.clipboard.writeText(uri).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="ui-code">{uri}</pre>
    </div>
  );
}

function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : String(failed);
}
