/** API keys: the servers' tokens of this environment, the keys each sign-in left, and a new token shown once. */

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { WORLD } from "../lib/world";
import { Copy } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { makeKey, readKeys, revokeKey, type Issued, type Key } from "./door";

const at = (iso: string | null): number | null => (iso === null ? null : Date.parse(iso) / 1000);
const used = (key: Key): string => (key.last_used_at === null ? "Never used" : `Used ${ago(at(key.last_used_at))}`);

/** Sign-ins sharing a device and a person, as one row: a console signed into sixty times is one line, not sixty. */
interface Bunch {
  label: string;
  who: string;
  keys: Key[];
  lastUsed: number | null;
}

function bunches(keys: readonly Key[]): Bunch[] {
  const by = new Map<string, Key[]>();
  for (const key of keys) by.set(`${key.label ?? ""}\u0000${key.name ?? ""}`, [...(by.get(`${key.label ?? ""}\u0000${key.name ?? ""}`) ?? []), key]);
  return [...by.values()]
    .map((group) => ({ label: group[0]?.label ?? "A sign-in", who: group[0]?.name ?? "", keys: group, lastUsed: group.map((key) => at(key.last_used_at)).reduce<number | null>((best, one) => (one !== null && (best === null || one > best) ? one : best), null) }))
    .sort((one, other) => (other.lastUsed ?? 0) - (one.lastUsed ?? 0));
}

function NewKeyPanel({ onMade, onClose }: { onMade: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const make = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    makeKey(credentials, { label: label.trim(), env: WORLD }).then(
      (made) => (setIssued(made), onMade()),
      (failed: unknown) => setRefused(saidBy(failed)),
    ).finally(() => setBusy(false));
  };
  if (issued !== null) {
    return (
      <SidePanel
        title={issued.label ?? "New key"}
        icon="check"
        about="Copy it now. It is shown this once, and kept nowhere it can be read back."
        closesOnEscape={false}
        onClose={onClose}
        footer={
          <div className="cfg-dialog-foot">
            <button type="button" className="cfg-save" onClick={onClose}>
              I copied it
            </button>
          </div>
        }
      >
        <div className="set-secret">
          <Copy text={issued.key} />
        </div>
        <p className="dash-quiet">Give it to your server as PINECALL_KEY. It acts in {issued.env} alone.</p>
      </SidePanel>
    );
  }
  return (
    <SidePanel
      title="New server key"
      icon="plus"
      about={`A token for a server of yours, in ${WORLD}. It belongs to the organization, not to you, and keeps working when you leave.`}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="new-key" className="cfg-save" disabled={busy || label.trim() === ""}>
              {busy ? "Making it…" : "Create key"}
            </button>
          </div>
        </>
      }
    >
      <form id="new-key" className="cfg-dialog-body" onSubmit={make}>
        <Field label="Name">
          <input className="cfg-input" aria-label="Name" placeholder="Backend, production" autoFocus value={label} onChange={(event) => setLabel(event.target.value)} />
        </Field>
      </form>
    </SidePanel>
  );
}

export function Keys(): ReactNode {
  const credentials = useCredentials();
  const [keys, setKeys] = useState<Key[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const stopMaking = useCallback(() => setMaking(false), []);
  const reread = useCallback((): void => void readKeys(credentials).then(setKeys, (failed: unknown) => (setKeys([]), setRefused(saidBy(failed)))), [credentials]);
  useEffect(reread, [reread]);

  const live = useMemo(() => (keys ?? []).filter((key) => key.revoked_at === null), [keys]);
  const servers = live.filter((key) => key.kind === "server").sort((one, other) => (at(other.last_used_at) ?? 0) - (at(one.last_used_at) ?? 0));
  const signIns = useMemo(() => bunches(live.filter((key) => key.kind === "person")), [live]);
  const revoke = (fingerprints: readonly string[]): void => {
    setRefused(null);
    Promise.all(fingerprints.map((one) => revokeKey(credentials, one))).then(reread, (failed: unknown) => (setRefused(saidBy(failed)), reread()));
  };

  return (
    <>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <section className="tst-list set-tone-accent" aria-label="Server keys">
        <header className="tst-head">
          <span className="tst-head-mark" aria-hidden="true">
            <Icon name="server" size={16} />
          </span>
          <span className="tst-head-words">
            <span className="tst-head-title">Server keys</span>
            <span className="tst-head-about">Tokens your servers call Pinecall with. Each acts in one environment.</span>
          </span>
          <button type="button" className="cfg-save tst-action" onClick={() => setMaking(true)}>
            <Icon name="plus" size={12} />
            New key
          </button>
        </header>
        {keys === null && <p className="dash-quiet tst-none">Reading…</p>}
        {servers.map((key) => (
          <div key={key.fingerprint} className="tst-row set-row">
            <span className="tst-row-words">
              <span className="tst-row-name">
                <span className="dash-clip">{key.label ?? key.fingerprint.slice(0, 12)}</span>
                <span className="tst-tag">{key.env ?? "both environments"}</span>
              </span>
              <span className="tst-row-under dash-clip">
                Made {ago(at(key.created_at))}
                {key.name === null ? "" : ` by ${key.name}`}
              </span>
            </span>
            <span className="tst-row-when">{used(key)}</span>
            <ConfirmButton label="Revoke" asks="Stop it for good?" danger onConfirm={() => revoke([key.fingerprint])} />
          </div>
        ))}
        {keys !== null && servers.length === 0 && <p className="dash-quiet tst-none">No server key yet.</p>}
      </section>

      <section className="tst-list set-tone-blue" aria-label="Sign-ins">
        <header className="tst-head">
          <span className="tst-head-mark" aria-hidden="true">
            <Icon name="personas" size={16} />
          </span>
          <span className="tst-head-words">
            <span className="tst-head-title">Sign-ins</span>
            <span className="tst-head-about">The keys each sign-in left: the console, the CLI, an assistant. Revoke one and that device signs in again.</span>
          </span>
        </header>
        {signIns.map((bunch) => {
          const id = `${bunch.label}\u0000${bunch.who}`;
          return (
            <div key={id}>
              <div className="tst-row set-row">
                <button type="button" className="tst-row-main" aria-expanded={open === id} onClick={() => setOpen(open === id ? null : id)}>
                  <span className="tst-row-words">
                    <span className="tst-row-name">
                      <span className="dash-clip">{bunch.label}</span>
                      {bunch.keys.length > 1 && <span className="tst-tag">{bunch.keys.length} keys</span>}
                    </span>
                    <span className="tst-row-under dash-clip">{bunch.who}</span>
                  </span>
                  <span className="tst-row-when">{bunch.lastUsed === null ? "Never used" : `Used ${ago(bunch.lastUsed)}`}</span>
                </button>
                <ConfirmButton label={bunch.keys.length > 1 ? "Revoke all" : "Revoke"} asks={bunch.keys.length > 1 ? `Stop all ${bunch.keys.length}?` : "Stop it for good?"} danger onConfirm={() => revoke(bunch.keys.map((key) => key.fingerprint))} />
              </div>
              {open === id &&
                bunch.keys.map((key) => (
                  <div key={key.fingerprint} className="tst-row set-row set-row-inner">
                    <span className="tst-row-words">
                      <span className="tst-row-under">Made {ago(at(key.created_at))}</span>
                    </span>
                    <span className="tst-row-when">{used(key)}</span>
                    <ConfirmButton label="Revoke" asks="Stop it?" danger onConfirm={() => revoke([key.fingerprint])} />
                  </div>
                ))}
            </div>
          );
        })}
        {keys !== null && signIns.length === 0 && <p className="dash-quiet tst-none">None.</p>}
      </section>
      {making && <NewKeyPanel onMade={reread} onClose={stopMaking} />}
    </>
  );
}
