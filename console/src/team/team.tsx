/** Team, the organization's page: its people and what each may do, the invitation that makes one more, and single sign-on. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../lib/org";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { readPeople, readSeats, type Person, type Seats } from "./door";
import { InvitePanel } from "./invite";
import { MemberPanel } from "./member";
import { ROLE_OPENS, STANDS } from "./roles";
import { SsoSection } from "./sso";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../apps/apps.css";
import "../numbers/numbers.css";
import "../test/test.css";
import "./team.css";

type Open = { panel: "invite" } | { panel: "member"; id: string };

function seatsOf(seats: Seats | null, people: number): string {
  if (seats === null) return people === 1 ? "1 person" : `${people} people`;
  return seats.limit === null ? `${seats.used} ${seats.used === 1 ? "seat" : "seats"}, no limit` : `${seats.used} of ${seats.limit} seats`;
}

export function TeamPage(): ReactNode {
  const credentials = useCredentials();
  const { agents, whose } = useOrg();
  const me = whose?.subject ?? null;
  const [people, setPeople] = useState<Person[] | null>(null);
  const [seats, setSeats] = useState<Seats | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const slugs = agents.map((one) => one.slug);

  const reread = useCallback(() => {
    readPeople(credentials).then(setPeople, (failed: unknown) => (setPeople([]), setRefused(saidBy(failed))));
    // A key that may not read the limits still reads the people.
    readSeats(credentials).then(setSeats, () => setSeats(null));
  }, [credentials]);

  useEffect(reread, [reread]);

  const openPerson = open?.panel === "member" ? (people ?? []).find((one) => one.id === open.id) : undefined;

  return (
    <>
      <PageHead />
      <div className="tst team">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}

        <section className="tst-list team-tone-blue" aria-label="People">
          <header className="tst-head">
            <span className="tst-head-mark" aria-hidden="true">
              <Icon name="team" size={16} />
            </span>
            <span className="tst-head-words">
              <span className="tst-head-title">People</span>
              <span className="tst-head-about">Who is in the org, and what their keys may do.</span>
            </span>
            {people !== null && people.length > 0 && <span className="tst-head-stands">{seatsOf(seats, people.length)}</span>}
            <button type="button" className="cfg-save tst-action" onClick={() => setOpen({ panel: "invite" })}>
              <Icon name="plus" size={12} />
              Invite
            </button>
          </header>
          {people === null && <p className="dash-quiet tst-none">Reading…</p>}
          {people !== null && people.length === 0 && refused === null && <p className="dash-quiet tst-none">Nobody is a member yet.</p>}
          {(people ?? []).map((one) => {
            const stands = STANDS[one.status];
            const production = one.role === "admin" || one.production;
            return (
              <div key={one.id} className={openPerson?.id === one.id ? "tst-row tst-row-on" : "tst-row"}>
                <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: "member", id: one.id })}>
                  <span className="tst-mark tst-mark-round" aria-hidden="true">
                    {(one.name.trim() || one.email).slice(0, 1).toUpperCase()}
                  </span>
                  <span className="tst-row-words">
                    <span className="tst-row-name">
                      <span className="dash-clip">{one.name}</span>
                      {one.id === me && <span className="tst-tag">you</span>}
                    </span>
                    <span className="tst-row-under dash-clip">{one.email}</span>
                  </span>
                  <span className="team-cell team-cell-role">{ROLE_OPENS[one.role].name}</span>
                  <span className={production ? "team-cell team-cell-on" : "team-cell"}>{production ? "Production" : "Sandbox only"}</span>
                  <span className={`tst-status tst-status-${stands.mood}`}>{stands.word}</span>
                </button>
              </div>
            );
          })}
        </section>

        <SsoSection />

        {open?.panel === "invite" && <InvitePanel agents={slugs} onInvited={reread} onClose={close} />}
        {openPerson !== undefined && <MemberPanel key={openPerson.id} person={openPerson} yourself={openPerson.id === me} agents={slugs} onChanged={reread} onRemoved={() => (close(), reread())} onClose={close} />}
      </div>
    </>
  );
}
