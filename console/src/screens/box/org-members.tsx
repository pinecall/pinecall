/** An org's people, as the box reads them: invite one without taking a seat, and say who runs the box. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Empty, Field, Input, Pill, Refused, Select, SelectItem, TableHead, TableRow, TextAction } from "../../ui";
import { inviteTo, makeOperator, readMembers, removeMember, type Invited } from "./door";
import { useDoor, useMove } from "./use-door";

const ROLES = ["admin", "manager", "developer", "supervisor", "qa"] as const;
const COLUMNS = "minmax(0,1fr) minmax(0,1.3fr) 100px 90px 220px";
const TONE = { active: "green", invited: "amber", disabled: "gray" } as const;

export function OrgMembers({ named, seats }: { named: string; seats: number | null }): ReactNode {
  const credentials = useCredentials();
  const people = useDoor(useCallback(() => readMembers(credentials, named), [credentials, named]));
  const acting = useMove();
  const [inviting, setInviting] = useState(false);
  const [invited, setInvited] = useState<Invited | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>("admin");
  const [removing, setRemoving] = useState<string | null>(null);

  const invite = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const sent = await acting.move(async () => {
      setInvited(await inviteTo(credentials, named, { email: email.trim(), name: name.trim(), role, agents: [] }));
      await people.reread();
    });
    if (sent) {
      setEmail("");
      setName("");
      setInviting(false);
    }
  };

  const then = (what: () => Promise<void>): void =>
    void acting.move(async () => {
      await what();
      await people.reread();
    });

  return (
    <>
      {invited !== null && <InvitationLink invited={invited} onClose={() => setInvited(null)} />}

      <Refused>{people.refused ?? acting.refused}</Refused>

      {people.value !== undefined && (
        <Card>
          <CardHead
            title="Members"
            meta={`${people.value.seated} seated${seats === null ? "" : ` of ${seats}`}`}
            action={
              inviting ? undefined : (
                <Button kind="primary" size="sm" className="ui-card-action" onClick={() => setInviting(true)}>
                  Invite someone
                </Button>
              )
            }
          />
          {inviting && (
            <div className="box-inline">
              <form className="ui-form" onSubmit={(event) => void invite(event)}>
                <Field label="Email" grow minWidth={180}>
                  <Input type="email" value={email} placeholder="name@company.com" onChange={(event) => setEmail(event.target.value)} required autoFocus />
                </Field>
                <Field label="Name" grow minWidth={150}>
                  <Input value={name} placeholder="Full name" onChange={(event) => setName(event.target.value)} required />
                </Field>
                <Field label="Role" minWidth={130}>
                  <Select value={role} onValueChange={(value) => setRole(value)}>
                    {ROLES.map((one) => (
                      <SelectItem key={one} value={one}>
                        {one}
                      </SelectItem>
                    ))}
                  </Select>
                </Field>
                <Button kind="primary" size="form" type="submit" disabled={acting.busy}>
                  {acting.busy ? "Inviting…" : "Invite"}
                </Button>
              </form>
              <div className="box-inline-foot">
                The box's invitation takes no seat: it is how an org gets its first admin.
                <span className="box-inline-close">
                  <TextAction onClick={() => setInviting(false)}>Close</TextAction>
                </span>
              </div>
            </div>
          )}
          {people.value.members.length === 0 ? (
            <Empty>Nobody has been invited to this org.</Empty>
          ) : (
            <>
              <TableHead columns={COLUMNS} labels={["Name", "Email", "Role", "Status", ""]} />
              {people.value.members.map((who) => (
                <TableRow key={who.id} columns={COLUMNS}>
                  <span className="ui-cell-strong box-line">
                    {who.name}
                    {who.operator === true && <Pill tone="violet" small>operator</Pill>}
                  </span>
                  <span className="ui-cell-ink ui-clip">{who.email}</span>
                  <span className="ui-cell-ink">{who.role}</span>
                  <span>
                    <Pill tone={TONE[who.status as keyof typeof TONE] ?? "gray"}>{who.status}</Pill>
                  </span>
                  <span className="ui-cell-end">
                    {removing === who.id ? (
                      <>
                        <TextAction danger disabled={acting.busy} onClick={() => then(() => removeMember(credentials, named, who.id).finally(() => setRemoving(null)))}>
                          Remove for good
                        </TextAction>
                        <TextAction onClick={() => setRemoving(null)}>Cancel</TextAction>
                      </>
                    ) : (
                      <>
                        {who.status === "active" && (
                          <TextAction disabled={acting.busy} onClick={() => then(() => makeOperator(credentials, named, who.id, who.operator !== true))}>
                            {who.operator === true ? "Stop running the box" : "Make operator"}
                          </TextAction>
                        )}
                        <TextAction danger onClick={() => setRemoving(who.id)}>
                          Remove
                        </TextAction>
                      </>
                    )}
                  </span>
                </TableRow>
              ))}
            </>
          )}
          <div className="ui-card-foot">Roles and agents are the org's own to change, from its Team screen. An operator's own key opens this box's doors as well as their org's.</div>
        </Card>
      )}
    </>
  );
}

/** The link an invitation is, shown the one time it exists in the clear. */
function InvitationLink({ invited, onClose }: { invited: Invited; onClose: () => void }): ReactNode {
  const [copied, setCopied] = useState(false);
  const token = invited.token ?? null;
  const link = token === null ? null : `${window.location.origin}/invitations/${encodeURIComponent(token)}`;
  return (
    <Card>
      <CardHead
        title={`${invited.member.name} is invited`}
        meta={invited.mailed === true ? "the link was mailed to them too" : link === null ? "they already have a password here: nothing to send" : "copy it now: it is never shown again"}
      >
        <span className="box-head-moves">
          {link !== null && (
            <Button size="xs" onClick={() => void navigator.clipboard.writeText(link).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
          <Button size="xs" onClick={onClose}>
            Done
          </Button>
        </span>
      </CardHead>
      {link !== null && <pre className="ui-code">{link}</pre>}
    </Card>
  );
}
