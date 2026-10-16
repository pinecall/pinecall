/** Team: three tabs — the org's people and the invitation that makes one more, what each role opens, and single sign-on. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { meIn } from "../../lib/corners";
import { useWhoami } from "../../lib/whoami";
import { Button, Card, CardHead, Empty, Field, Input, Page, PageHead, Refused, Select, SelectItem, Switch, TableHead, Tabs, TextAction } from "../../ui";
import { change, invite, readMembers, removeMember, resetLink, ROLES, type Invited, type Member } from "./door";
import { COLUMNS, MemberRow } from "./member-row";
import { Roles } from "./roles";
import { SingleSignOn } from "./sso";
import "./team.css";

type Tab = "people" | "roles" | "sso";

const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "people", name: "People" },
  { tab: "roles", name: "Roles" },
  { tab: "sso", name: "Single sign-on" },
];

/**
 * The screen. A member is a row, made by a one-use invitation the person accepts with a
 * password; their keys are their own from then on, with the scopes their role presets. Disabling
 * one keeps the row, revokes their keys and refuses their login. Every refusal is the gateway's
 * sentence, verbatim. The tab is in the address (`?tab=`), so a reload lands on the same one.
 */
export function Team(): ReactNode {
  const credentials = useCredentials();
  const me = meIn(useWhoami());
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some((one) => one.tab === params.get("tab")) ? (params.get("tab") as Tab) : "people";
  const [members, setMembers] = useState<Member[] | null>(null);
  const [inviting, setInviting] = useState(false);
  const [invited, setInvited] = useState<{ link: Invited; kind: "invitation" | "reset" } | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = async (): Promise<void> => setMembers(await readMembers(credentials));
  const pick = (picked: Tab): void => setParams(picked === "people" ? {} : { tab: picked });

  useEffect(() => {
    let gone = false;
    readMembers(credentials).then(
      (listed) => {
        if (!gone) setMembers(listed);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const changed = async (id: string, said: Parameters<typeof change>[2]): Promise<void> => {
    setRefused(null);
    try {
      await change(credentials, id, said);
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  // An invitation, first or again: the gateway mints a fresh one-use link for an email it already
  // holds as invited, and takes no second seat for it.
  const inviteOne = async (who: Parameters<typeof invite>[1]): Promise<boolean> => {
    setRefused(null);
    try {
      setInvited({ link: await invite(credentials, who), kind: "invitation" });
      await reread();
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    }
  };

  const remove = async (id: string): Promise<void> => {
    setRefused(null);
    try {
      await removeMember(credentials, id);
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const reset = async (id: string): Promise<void> => {
    setRefused(null);
    try {
      setInvited({ link: await resetLink(credentials, id), kind: "reset" });
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const standing = (status: Member["status"]): number => (members ?? []).filter((member) => member.status === status).length;

  return (
    <Page width={1060} tight>
      <PageHead title="Team" lede="The org's people: who they are, what their keys may do, and how they sign in." />

      <Tabs label="Team" tabs={TABS} on={tab} onPick={pick} />

      {tab === "people" && (
        <>
          {invited !== null && <InvitationLink invited={invited.link} kind={invited.kind} onClose={() => setInvited(null)} />}

          <Refused>{refused}</Refused>

          {members !== null && (
            <Card>
              <CardHead
                title="People"
                meta={[`${standing("active")} active`, standing("invited") > 0 && `${standing("invited")} invited`, standing("disabled") > 0 && `${standing("disabled")} disabled`]
                  .filter(Boolean)
                  .join(" · ")}
                action={
                  inviting ? undefined : (
                    <Button kind="primary" size="sm" className="ui-card-action" onClick={() => setInviting(true)}>
                      Invite someone
                    </Button>
                  )
                }
              />
              {inviting && (
                <InviteForm
                  onInvite={async (who) => {
                    if (await inviteOne(who)) setInviting(false);
                  }}
                  onClose={() => setInviting(false)}
                  onRoles={() => pick("roles")}
                />
              )}
              {members.length === 0 ? (
                <Empty>Nobody is a member yet: the org's machine key alone opens its doors. Invite the first person.</Empty>
              ) : (
                <>
                  <TableHead columns={COLUMNS} labels={["Name", "Email", "Role", "Agents", "Production", "Status>", ""]} />
                  {members.map((member) => (
                    <MemberRow
                      key={member.id}
                      member={member}
                      onChange={(said) => changed(member.id, said)}
                      onResend={async () => {
                        await inviteOne({ email: member.email, name: member.name, role: member.role, agents: member.agents, production: member.production });
                      }}
                      onReset={() => reset(member.id)}
                      onRemove={() => remove(member.id)}
                      yourself={member.id === me}
                    />
                  ))}
                </>
              )}
            </Card>
          )}
        </>
      )}

      {tab === "roles" && <Roles />}

      {tab === "sso" && <SingleSignOn />}
    </Page>
  );
}

/** The link an invitation is, shown the one time it exists in the clear — or why there is none to show. */
function InvitationLink({ invited, kind, onClose }: { invited: Invited; kind: "invitation" | "reset"; onClose: () => void }): ReactNode {
  const [copied, setCopied] = useState(false);
  const title = kind === "reset" ? `A new password for ${invited.member.name}` : `${invited.member.name} is invited`;
  if (invited.token === null) {
    return (
      <Card>
        <CardHead title={title} meta={whyNoLink(invited, kind)}>
          <Button size="xs" onClick={onClose}>
            Done
          </Button>
        </CardHead>
      </Card>
    );
  }
  const link = invitationLink(invited.token);
  return (
    <Card>
      <CardHead title={title} meta="copy it now: the table keeps the fingerprint, and it is never shown again">
        <span className="team-link-moves">
          <Button
            size="xs"
            onClick={() => {
              void navigator.clipboard.writeText(link).then(() => setCopied(true));
            }}
          >
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button size="xs" onClick={onClose}>
            Done
          </Button>
        </span>
      </CardHead>
      <pre className="ui-code">{link}</pre>
      <div className="ui-card-foot">
        {kind === "reset"
          ? `One use · dies ${invited.expires_at} · hand it to them: it opens the card where they choose a new password. Any older link of theirs no longer opens.`
          : `One use · dies ${invited.expires_at} · it opens a card where they choose their password and take their first key.`}
      </div>
    </Card>
  );
}

/** The three things an invitation names, and the agents when it is not every one of them — inside the people card. */
function InviteForm({
  onInvite,
  onClose,
  onRoles,
}: {
  onInvite: (who: Parameters<typeof invite>[1]) => Promise<void>;
  onClose: () => void;
  onRoles: () => void;
}): ReactNode {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Member["role"]>("qa");
  const [agents, setAgents] = useState("");
  const [production, setProduction] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    try {
      await onInvite({
        email: email.trim(),
        name: name.trim(),
        role,
        agents: agents.split(/[\s,]+/).filter((one) => one !== ""),
        production,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="team-invite">
      <form className="ui-form" onSubmit={(event) => void submit(event)}>
        <Field label="Email" grow minWidth={180}>
          <Input placeholder="name@company.com" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoFocus />
        </Field>
        <Field label="Name" grow minWidth={150}>
          <Input placeholder="Full name" value={name} onChange={(event) => setName(event.target.value)} required />
        </Field>
        <Field label="Role" minWidth={130}>
          <Select value={role} onValueChange={(value) => setRole(value as Member["role"])}>
            {ROLES.map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </Select>
        </Field>
        <Field label="Agents" minWidth={150}>
          <Input placeholder="every agent" value={agents} onChange={(event) => setAgents(event.target.value)} />
        </Field>
        <Field label="Production" minWidth={90}>
          {role === "admin" ? (
            <span className="ui-cell-faint">always</span>
          ) : (
            <Switch on={production} label="acts in production" onChange={setProduction} />
          )}
        </Field>
        <Button kind="primary" size="form" type="submit" disabled={busy}>
          {busy ? "Inviting…" : "Invite"}
        </Button>
      </form>
      <div className="team-roles">
        A role is a preset of what their keys open — <TextAction onClick={onRoles}>see what each one does</TextAction>
        <span className="team-invite-close">
          <TextAction onClick={onClose}>Close</TextAction>
        </span>
      </div>
    </div>
  );
}

function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : String(failed);
}

// A link chooses the person's ONE password, in every org of theirs, so the gateway hands it to an
// admin only for somebody who is this org's alone (the runtime's docs/protocol/people.md).
/** Why the gateway handed this admin no link: seated already, or the link is the person's to open. */
function whyNoLink(invited: Invited, kind: "invitation" | "reset"): string {
  if (kind === "invitation" && invited.member.status === "active") {
    return "already a person on this box: seated, they sign in with the password they have";
  }
  const posted = invited.mailed ? "it was posted to them" : "this box posts no mail, so they use the link their other org sent, or Forgot your password? where mail is set up";
  return `also somebody else's on this box, so the link is theirs alone — ${posted}`;
}

/** Where an invited person opens the console: the card at /invitations/<token>, on this same origin. */
function invitationLink(token: string): string {
  return `${window.location.origin}/invitations/${encodeURIComponent(token)}`;
}
