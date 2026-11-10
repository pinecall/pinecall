/** An invitation written in the side panel: who, their role, their agents, production; then the link, shown once. */

import { useId, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { useMove } from "../numbers/parts";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { AccessFields, accessOf, draftOf, LinkOnce, type Draft } from "./access";
import { invite, type Linked } from "./door";

export function InvitePanel({ agents, onInvited, onClose }: { agents: readonly string[]; onInvited: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const form = useId();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<Draft>(() => draftOf({ role: "qa", agents: [], production: false }));
  const [linked, setLinked] = useState<Linked | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const { busy, refused, move } = useMove();

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    const access = accessOf(draft);
    if (typeof access === "string") return setMissing(access);
    setMissing(null);
    void move(() => invite(credentials, { email: email.trim(), name: name.trim(), ...access })).then(
      (answer) => {
        setLinked(answer);
        onInvited();
      },
      () => undefined,
    );
  };

  if (linked !== null) {
    return (
      <SidePanel
        title="Invitation"
        icon="team"
        about={`${linked.member.email} takes a seat as ${linked.member.role}.`}
        onClose={onClose}
        footer={
          <div className="cfg-dialog-foot">
            <button type="button" className="cfg-save" onClick={onClose}>
              Done
            </button>
          </div>
        }
      >
        <LinkOnce linked={linked} kind="invitation" />
      </SidePanel>
    );
  }

  const said = missing ?? refused;
  return (
    <SidePanel
      title="Invite someone"
      icon="team"
      about="They get a one-use link, choose a password and take their first key."
      onClose={onClose}
      footer={
        <>
          {said !== null && (
            <p className="cfg-refused" role="alert">
              {said}
            </p>
          )}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form={form} className="cfg-save" disabled={busy}>
              {busy ? "Inviting…" : "Invite"}
            </button>
          </div>
        </>
      }
    >
      <form id={form} className="cfg-dialog-body" onSubmit={submit}>
        <Field label="Email">
          <input className="cfg-input" type="email" aria-label="Email" placeholder="name@company.com" autoFocus required value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label="Name">
          <input className="cfg-input" aria-label="Name" placeholder="Full name" required value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <AccessFields draft={draft} agents={agents} onChange={setDraft} />
      </form>
    </SidePanel>
  );
}
