/** One member open in the side panel: how they stand, what they may do, a new link for them, and the way out of the org. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { useMove } from "../numbers/parts";
import { Field } from "../ui/setting";
import { AccessFields, accessOf, draftOf, LinkOnce, type Draft } from "./access";
import { changePerson, invite, removePerson, resetLink, type Linked, type Person } from "./door";
import { STANDS } from "./roles";

const STANDS_AS: Record<Person["status"], string> = {
  active: "Signs in and holds keys.",
  invited: "Has not opened the invitation yet.",
  disabled: "Keys revoked, sign-in refused. The seat is kept.",
};

/** `onChanged` after anything was written; `onRemoved` once the person is out. */
export function MemberPanel({ person, yourself, agents, onChanged, onRemoved, onClose }: { person: Person; yourself: boolean; agents: readonly string[]; onChanged: () => void; onRemoved: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [draft, setDraft] = useState<Draft>(() => draftOf(person));
  const [saving, setSaving] = useState(false);
  const [unsaved, setUnsaved] = useState<string | null>(null);
  const [linked, setLinked] = useState<{ link: Linked; kind: "invitation" | "reset" } | null>(null);
  const { busy, refused, move } = useMove();
  const stands = STANDS[person.status];

  const save = async (): Promise<void> => {
    const access = accessOf(draft);
    if (typeof access === "string") return setUnsaved(access);
    const said: Parameters<typeof changePerson>[2] = {};
    if (access.role !== person.role) said.role = access.role;
    if (access.agents.join(" ") !== [...person.agents].sort().join(" ")) said.agents = access.agents;
    // An admin's production is the gateway's to say, never sent.
    if (access.role !== "admin" && access.production !== person.production) said.production = access.production;
    if (Object.keys(said).length === 0) return onClose();
    setSaving(true);
    setUnsaved(null);
    try {
      await changePerson(credentials, person.id, said);
      onChanged();
      onClose();
    } catch (failed) {
      setUnsaved(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  // The panel stays open after a move: the row behind it is read again.
  const stand = (status: Person["status"]): void => void move(() => changePerson(credentials, person.id, { status })).then(onChanged, () => undefined);
  const reset = (): void => void move(() => resetLink(credentials, person.id)).then((link) => setLinked({ link, kind: "reset" }), () => undefined);
  const again = (): void =>
    void move(() => invite(credentials, { email: person.email, name: person.name, role: person.role, agents: person.agents, production: person.production })).then((link) => setLinked({ link, kind: "invitation" }), () => undefined);
  const remove = (): void => void move(() => removePerson(credentials, person.id)).then(onRemoved, () => undefined);

  return (
    <EditDialog title={person.name} icon="personas" about={person.email} saving={saving} refused={unsaved ?? refused} onSave={() => void save()} onClose={onClose}>
      <div className={`tst-last tst-last-${stands.mood}`}>
        <span className="tst-last-top">
          <b>{stands.word}</b>
          <span className="dash-quiet">{[yourself && "You", person.operator === true && "Runs this gateway", person.verified === false && person.status === "active" && "Email not verified"].filter(Boolean).join(" · ")}</span>
        </span>
        <span>{STANDS_AS[person.status]}</span>
      </div>
      {linked !== null && <LinkOnce linked={linked.link} kind={linked.kind} />}
      <AccessFields draft={draft} agents={agents} onChange={setDraft} />
      <Field label="Sign-in">
        <div className="team-moves">
          {person.status === "active" && (
            <button type="button" className="app-button" disabled={busy} onClick={reset}>
              Password reset link
            </button>
          )}
          {person.status === "invited" && (
            <button type="button" className="app-button" disabled={busy} onClick={again}>
              New invitation link
            </button>
          )}
          {person.status === "active" && <ConfirmButton label="Disable" asks="Revoke their keys?" onConfirm={() => stand("disabled")} />}
          {person.status === "disabled" && (
            <button type="button" className="app-button" disabled={busy} onClick={() => stand("active")}>
              Enable
            </button>
          )}
          <ConfirmButton label="Remove from the org" asks="Remove for good?" danger onConfirm={remove} />
        </div>
      </Field>
    </EditDialog>
  );
}
