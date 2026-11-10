/** What a person may do, as the fields an invitation and a change share: the role, the agents, production; and a link shown its one time. */

import type { ReactNode } from "react";

import { Copy } from "../numbers/parts";
import { Select } from "../ui/select";
import { Field, Setting, Toggle } from "../ui/setting";
import { linkOf, type Access, type Linked, type Role } from "./door";
import { ROLE_ITEMS, ROLE_OPENS } from "./roles";

/** The form's own state: a chosen set is kept while "every agent" is picked, so switching back loses nothing. */
export interface Draft {
  role: Role;
  every: boolean;
  chosen: string[];
  production: boolean;
}

export const draftOf = (access: Access): Draft => ({ role: access.role, every: access.agents.length === 0, chosen: access.agents, production: access.production });

/** What the gateway is told, or the sentence that says why not yet. */
export function accessOf(draft: Draft): Access | string {
  if (!draft.every && draft.chosen.length === 0) return "Choose at least one agent, or every agent.";
  // An admin always acts in production: the switch is not theirs to turn.
  return { role: draft.role, agents: draft.every ? [] : [...draft.chosen].sort(), production: draft.role === "admin" ? true : draft.production };
}

export function AccessFields({ draft, agents, onChange }: { draft: Draft; agents: readonly string[]; onChange: (draft: Draft) => void }): ReactNode {
  // An agent nobody holds any more stays in the set until it is taken out.
  const slugs = [...new Set([...agents, ...draft.chosen])].sort();
  const admin = draft.role === "admin";
  const flip = (slug: string): void => onChange({ ...draft, chosen: draft.chosen.includes(slug) ? draft.chosen.filter((one) => one !== slug) : [...draft.chosen, slug] });
  return (
    <>
      <Field label="Role">
        <Select label="Role" searchable={false} items={ROLE_ITEMS} value={draft.role} onChange={(role) => onChange({ ...draft, role: role as Role })} />
        <span className="team-opens">Opens {ROLE_OPENS[draft.role].opens}</span>
      </Field>
      <Field label="Agents">
        <div className="dash-switch team-which" role="group" aria-label="Which agents">
          <button type="button" aria-pressed={draft.every} className={draft.every ? "dash-switch-on" : ""} onClick={() => onChange({ ...draft, every: true })}>
            Every agent
          </button>
          <button type="button" aria-pressed={!draft.every} className={draft.every ? "" : "dash-switch-on"} onClick={() => onChange({ ...draft, every: false })}>
            Chosen
          </button>
        </div>
        {!draft.every &&
          (slugs.length === 0 ? (
            <p className="dash-quiet">No agent yet.</p>
          ) : (
            <div className="team-agents">
              {slugs.map((slug) => (
                <button key={slug} type="button" aria-pressed={draft.chosen.includes(slug)} className={draft.chosen.includes(slug) ? "team-agent team-agent-on" : "team-agent"} onClick={() => flip(slug)}>
                  {slug}
                </button>
              ))}
            </div>
          ))}
      </Field>
      <Setting icon="server" title="Production" about={admin ? "An admin always acts in production." : "May act on the live agents. The sandbox is always open."} aside={<Toggle on={admin || draft.production} disabled={admin} label="Acts in production" onChange={(production) => onChange({ ...draft, production })} />} />
    </>
  );
}

// A link chooses the person's one password, in every org of theirs: the gateway hands it to an admin only for somebody who is this org's alone.
function whyNoLink(linked: Linked, kind: "invitation" | "reset"): string {
  if (kind === "invitation" && linked.member.status === "active") return "Already a person on this gateway. They sign in with the password they have.";
  return linked.mailed ? "The link was mailed to them. It is theirs alone, so it is not shown here." : "The link is theirs alone, and this gateway sends no mail. They use Forgot your password on the sign-in page.";
}

/** The link an invitation or a reset is, the one time it exists in the clear; or why there is none to show. */
export function LinkOnce({ linked, kind }: { linked: Linked; kind: "invitation" | "reset" }): ReactNode {
  const title = kind === "reset" ? `A new password for ${linked.member.name}` : `${linked.member.name} is invited`;
  return (
    <div className="team-link" role="status">
      <b>{title}</b>
      {linked.token === null ? (
        <span>{whyNoLink(linked, kind)}</span>
      ) : (
        <>
          <Copy text={linkOf(linked.token)} />
          <span>
            Copy it now: it is not shown again. One use{linked.expires_at == null ? "" : `, until ${new Date(linked.expires_at).toLocaleString()}`}.
          </span>
        </>
      )}
    </div>
  );
}
