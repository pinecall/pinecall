/** Single sign-on: whether the org has a provider, the redirect URI to register there, and its form in the side panel. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { Copy, useMove } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Field, Setting, Toggle } from "../ui/setting";
import { readSso, removeSso, saveSso, type Role, type Sso } from "./door";
import { ROLE_ITEMS, ROLE_OPENS } from "./roles";

// Nobody arrives new: a person the provider vouches for is invited first.
const NOBODY = "";

const hostOf = (issuer: string): string => {
  try {
    return new URL(issuer).host;
  } catch {
    return issuer;
  }
};

function SsoPanel({ sso, onSaved, onRemoved, onClose }: { sso: Sso; onSaved: (kept: Sso) => void; onRemoved: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [issuer, setIssuer] = useState(sso.issuer ?? "");
  const [clientId, setClientId] = useState(sso.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [domains, setDomains] = useState(sso.domains.join(", "));
  const [role, setRole] = useState<string>(sso.role ?? NOBODY);
  const [required, setRequired] = useState(sso.required);
  const saving = useMove();
  const removing = useMove();
  const unproved = (sso.proofs ?? []).filter((one) => !one.verified);

  const save = (): void =>
    void saving
      .move(() =>
        saveSso(credentials, {
          issuer: issuer.trim(),
          client_id: clientId.trim(),
          client_secret: secret,
          domains: domains.split(/[\s,]+/).filter((one) => one !== ""),
          role: role === NOBODY ? null : (role as Role),
          required,
        }),
      )
      .then(onSaved, () => undefined);

  return (
    <EditDialog title="Single sign-on" icon="privacy" about="Any OpenID provider: Google Workspace, Okta, Entra. The gateway asks the issuer for its discovery document before it keeps anything." saving={saving.busy} refused={saving.refused ?? removing.refused} onSave={save} onClose={onClose}>
      <Field label="Redirect URI">
        <Copy text={sso.redirect_uri} />
        <span className="team-opens">Register it at the provider.</span>
      </Field>
      <Field label="Issuer URL">
        <input className="cfg-input" type="url" aria-label="Issuer URL" placeholder="https://accounts.google.com" required value={issuer} onChange={(event) => setIssuer(event.target.value)} />
      </Field>
      <Field label="Client ID">
        <input className="cfg-input" aria-label="Client ID" required value={clientId} onChange={(event) => setClientId(event.target.value)} />
      </Field>
      <Field label="Client secret">
        <input className="cfg-input" type="password" autoComplete="off" aria-label="Client secret" placeholder={sso.configured ? "Type it again: it is never read back" : "Sent once, never shown again"} required value={secret} onChange={(event) => setSecret(event.target.value)} />
      </Field>
      <Field label="Domains">
        <input className="cfg-input" aria-label="Domains" placeholder="company.com, other.com" required value={domains} onChange={(event) => setDomains(event.target.value)} />
        {unproved.map((one) => (
          <div key={one.domain} className="team-proof">
            <span>
              <b>{one.domain}</b> signs nobody in yet. Publish this TXT record at the domain.
            </span>
            {one.txt != null && <Copy text={one.txt} />}
          </div>
        ))}
      </Field>
      <Field label="People who arrive new">
        <Select label="People who arrive new" searchable={false} items={[{ value: NOBODY, label: "Nobody", detail: "Invite a person first" }, ...ROLE_ITEMS]} value={role} onChange={setRole} />
      </Field>
      <Setting icon="privacy" title="Required" about="Passwords stop working for this org." aside={<Toggle on={required} label="Single sign-on is required" onChange={setRequired} />} />
      {sso.configured && (
        <Field label="Remove the provider">
          <div className="team-moves">
            <ConfirmButton label="Remove" asks="Back to passwords?" danger onConfirm={() => void removing.move(() => removeSso(credentials)).then(onRemoved, () => undefined)} />
          </div>
        </Field>
      )}
    </EditDialog>
  );
}

/** The section. Nothing is drawn on a gateway that has no single sign-on. */
export function SsoSection(): ReactNode {
  const credentials = useCredentials();
  const [sso, setSso] = useState<Sso | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const reread = useCallback(() => readSso(credentials).then(setSso, (failed: unknown) => setRefused(saidBy(failed))), [credentials]);

  useEffect(() => {
    void reread();
  }, [reread]);

  if (sso === null && refused === null) return null;
  const unproved = (sso?.proofs ?? []).filter((one) => !one.verified).length;

  return (
    <section className="tst-list team-tone-pink" aria-label="Single sign-on">
      <header className="tst-head">
        <span className="tst-head-mark" aria-hidden="true">
          <Icon name="privacy" size={16} />
        </span>
        <span className="tst-head-words">
          <span className="tst-head-title">Single sign-on</span>
          <span className="tst-head-about">People sign in with the org's identity provider.</span>
        </span>
        {sso !== null && !sso.configured && (
          <button type="button" className="cfg-save tst-action" onClick={() => setOpen(true)}>
            <Icon name="plus" size={12} />
            Set up
          </button>
        )}
      </header>
      {refused !== null && (
        <p className="cfg-refused tst-none" role="alert">
          {refused}
        </p>
      )}
      {sso !== null && !sso.configured && <p className="dash-quiet tst-none">Not set up. People sign in with a password.</p>}
      {sso !== null && sso.configured && (
        <div className={open ? "tst-row tst-row-on" : "tst-row"}>
          <button type="button" className="tst-row-main" onClick={() => setOpen(true)}>
            <span className="tst-mark" aria-hidden="true">
              <Icon name="privacy" size={14} />
            </span>
            <span className="tst-row-words">
              <span className="tst-row-name">
                <span className="dash-clip">{hostOf(sso.issuer ?? "")}</span>
                <span className="tst-tag">{sso.required ? "required" : "beside passwords"}</span>
              </span>
              <span className="tst-row-under dash-clip">
                {sso.domains.join(", ")}
                {sso.role != null && sso.role in ROLE_OPENS ? `. New people arrive as ${ROLE_OPENS[sso.role as Role].name}.` : ""}
              </span>
            </span>
            <span className={`tst-status team-status tst-status-${unproved === 0 ? "held" : "waiting"}`}>{unproved === 0 ? "On" : unproved === 1 ? "1 domain to prove" : `${unproved} domains to prove`}</span>
          </button>
        </div>
      )}
      {sso !== null && (
        <div className="team-redirect">
          <span>Redirect URI</span>
          <Copy text={sso.redirect_uri} bare />
        </div>
      )}
      {open && sso !== null && <SsoPanel sso={sso} onSaved={(kept) => (setSso(kept), close())} onRemoved={() => (close(), void reread())} onClose={close} />}
    </section>
  );
}
