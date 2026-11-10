/** Organizations, the operator's: every org of the box in a list, and the one open with how its simulations are shaped, to change, and its monthly limits, each environment's to change. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Navigate, NavLink, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { count } from "../lib/format";
import { useOrg } from "../lib/org";
import { PageHead } from "../shell/page-head";
import { readOrg, readOrgs, saveShape, USUAL, WORLDS, type OneOrg, type Org, type Shape, type World, type WorldQuotas } from "./door";
import { ABOUT } from "./limit-fields";
import { OrgLimitsPanel } from "./org-limits";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "./box.css";

const HOME = "/box/orgs";
const WORLD_NAMES: Record<World, string> = { sandbox: "Sandbox", production: "Production" };
// The most each may be given, as the door takes them.
const MOST = { simulations_at_once: 200, comparison_calls: 500 } as const;

const FIELDS: readonly { name: keyof Shape; title: string; about: string }[] = [
  { name: "simulations_at_once", title: "Simulated calls at once", about: "How many pretend callers may be on the line together. Each takes a seat of the fleet a real caller would." },
  { name: "comparison_calls", title: "Calls in one comparison", about: "Tasks × setups × repeats. Past the calls at once, the rest wait their turn." },
];

const rowClass = ({ isActive }: { isActive: boolean }): string => (isActive ? "app-row app-row-on" : "app-row");

function written(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

// Empty is the platform's own, never zero: zero refuses every simulation.
function read(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

/** One world's shape: two numbers, each empty for the platform's own, saved together. */
function ShapeForm({ org, world, standing, onSaved }: { org: string; world: World; standing: WorldQuotas | undefined; onSaved: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const [typed, setTyped] = useState<Record<keyof Shape, string>>({ simulations_at_once: written(standing?.simulations_at_once), comparison_calls: written(standing?.comparison_calls) });
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  const wanted: Shape = { simulations_at_once: read(typed.simulations_at_once), comparison_calls: read(typed.comparison_calls) };
  const changed = FIELDS.some((field) => wanted[field.name] !== (standing?.[field.name] ?? null));
  const wrong = FIELDS.find((field) => {
    const value = wanted[field.name];
    return value !== null && (!Number.isInteger(value) || value < 0 || value > MOST[field.name]);
  });

  const save = async (): Promise<void> => {
    setSaving(true);
    setSaid(null);
    try {
      await saveShape(credentials, org, world, wanted);
      await onSaved();
      setSaid({ tone: "good", text: "Saved. It holds from the next simulation placed." });
    } catch (failed) {
      setSaid({ tone: "bad", text: saidBy(failed) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="box-world">
      <span className="box-world-name">{WORLD_NAMES[world]}</span>
      <div className="box-fields">
        {FIELDS.map((field) => (
          <label key={field.name} className="box-field">
            <span className="box-field-title">{field.title}</span>
            <input
              className="cfg-input"
              type="number"
              inputMode="numeric"
              min={0}
              max={MOST[field.name]}
              placeholder={`${USUAL[field.name]}, the platform's own`}
              value={typed[field.name]}
              onChange={(event) => {
                setSaid(null);
                setTyped({ ...typed, [field.name]: event.target.value });
              }}
            />
            <span className="dash-quiet">{field.about}</span>
          </label>
        ))}
      </div>
      <div className="box-end">
        {wrong !== undefined && <span className="app-refused">{wrong.title}: a whole number from 0 to {MOST[wrong.name]}, or empty.</span>}
        {wrong === undefined && said !== null && <span className={said.tone === "good" ? "dash-mood-good box-said" : "app-refused"}>{said.text}</span>}
        <button type="button" className="app-button box-save" disabled={saving || !changed || wrong !== undefined} onClick={() => void save()}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

function limitSaid(value: number | null | undefined): string {
  return value === null || value === undefined ? "No limit" : count(value);
}

function OrgView({ org, onChanged }: { org: OneOrg; onChanged: () => Promise<void> }): ReactNode {
  const named = [...new Set(WORLDS.flatMap((world) => Object.keys(org.quotas[world]?.limits ?? {})))];
  const [editing, setEditing] = useState<World | null>(null);
  return (
    <div className="app-main">
      <section className="dash-card" aria-label="How it stands">
        <div className="dash-card-top">
          <span className="dash-eyebrow">Holding now</span>
          <span className="dash-quiet box-id">{org.id}</span>
        </div>
        <dl className="dash-facts box-holding">
          <div>
            <dt className="dash-quiet">Seats</dt>
            <dd>{count(org.holding.seats)}</dd>
          </div>
          <div>
            <dt className="dash-quiet">Numbers</dt>
            <dd>{count(org.holding.numbers)}</dd>
          </div>
          <div>
            <dt className="dash-quiet">Remembered facts</dt>
            <dd>{count(org.holding.memory_facts)}</dd>
          </div>
          <div>
            <dt className="dash-quiet">Knowledge chunks</dt>
            <dd>{count(org.holding.knowledge_chunks)}</dd>
          </div>
        </dl>
      </section>

      <section className="dash-card" aria-label="Simulations">
        <div className="dash-card-top">
          <span className="dash-eyebrow">Simulations</span>
          <span className="dash-quiet">Left empty, the platform's own. Writing the monthly limits never resets these.</span>
        </div>
        <div className="box-worlds">
          {WORLDS.map((world) => (
            <ShapeForm key={`${org.id}:${world}:${org.quotas[world]?.simulations_at_once ?? ""}:${org.quotas[world]?.comparison_calls ?? ""}`} org={org.slug} world={world} standing={org.quotas[world]} onSaved={onChanged} />
          ))}
        </div>
      </section>

      <section className="dash-card" aria-label="Monthly limits">
        <div className="dash-card-top">
          <span className="dash-eyebrow">Monthly limits</span>
          <span className="box-limit-edits">
            {WORLDS.map((world) => (
              <button key={world} type="button" className="app-button" onClick={() => setEditing(world)}>
                Edit {WORLD_NAMES[world].toLowerCase()}
              </button>
            ))}
          </span>
        </div>
        <div className="dash-rows">
          <div className="box-limit dash-row-head">
            <span>Limit</span>
            {WORLDS.map((world) => (
              <span key={world} className="dash-num">
                {WORLD_NAMES[world]}
              </span>
            ))}
          </div>
          {named.map((limit) => (
            <div key={limit} className="box-limit dash-row">
              <span className="dash-first">{(ABOUT as Record<string, { name: string } | undefined>)[limit]?.name ?? limit.replace(/_/g, " ")}</span>
              {WORLDS.map((world) => {
                const value = org.quotas[world]?.limits[limit];
                return (
                  <span key={world} className={value === null || value === undefined ? "dash-num dash-quiet" : "dash-num"}>
                    {limitSaid(value)}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </section>
      {editing !== null && <OrgLimitsPanel key={editing} org={org} world={editing} worldName={WORLD_NAMES[editing]} onSaved={onChanged} onClose={() => setEditing(null)} />}
    </div>
  );
}

export function OrgsPage(): ReactNode {
  const credentials = useCredentials();
  const { org: asked } = useParams();
  const { orgs: memberships } = useOrg();
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  const [open, setOpen] = useState<OneOrg | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let gone = false;
    readOrgs(credentials).then(
      (read) => !gone && setOrgs(read),
      (failed) => {
        if (gone) return;
        setOrgs([]);
        setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const reread = useCallback(async (): Promise<void> => {
    if (asked === undefined) return;
    try {
      setOpen(await readOrg(credentials, asked));
      setRefused(null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  }, [credentials, asked]);

  useEffect(() => {
    setOpen(null);
    void reread();
  }, [reread]);

  const first = orgs?.[0];
  if (asked === undefined && first !== undefined) return <Navigate to={`${HOME}/${encodeURIComponent(first.slug)}`} replace />;

  const typed = filter.trim().toLowerCase();
  const shown = (orgs ?? []).filter((one) => `${one.slug} ${one.name}`.toLowerCase().includes(typed));
  const here = orgs?.find((one) => one.slug === asked);
  // The ones the person belongs to first; the rest are every other org of the deployment, seen as its operator.
  const mine = new Set((memberships ?? []).filter((one) => one.member !== false).map((one) => one.slug));
  const groups = [
    { label: "Yours", rows: shown.filter((one) => mine.has(one.slug)) },
    { label: "Others", rows: shown.filter((one) => !mine.has(one.slug)) },
  ].filter((group) => group.rows.length > 0);

  return (
    <>
      <PageHead open={here?.name ?? asked} />
      <div className="app-layout">
        <aside className="app-list" aria-label="Organizations">
          <div className="app-list-head">
            <span className="app-list-title">Organizations</span>
            <span className="dash-quiet">{orgs === null ? "" : orgs.length}</span>
          </div>
          <input className="app-input app-search" aria-label="Search organizations" placeholder="Search organizations" value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {groups.map((group) => (
              <div key={group.label} className="box-group">
                <div className="box-group-label">
                  {group.label}
                  <span>{group.rows.length}</span>
                </div>
                {group.rows.map((one) => (
                  <NavLink key={one.id} to={`${HOME}/${encodeURIComponent(one.slug)}`} className={({ isActive }) => `${rowClass({ isActive })} box-org`}>
                    <span className="box-org-mark" aria-hidden="true">
                      {(one.name.trim() || one.slug).charAt(0).toUpperCase()}
                    </span>
                    <span className="box-org-words">
                      <span className="dash-clip">{one.name}</span>
                      <span className="app-row-under dash-clip">{one.slug}</span>
                    </span>
                  </NavLink>
                ))}
              </div>
            ))}
            {orgs !== null && orgs.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
        </aside>
        <div className="app-open">
          {refused !== null && <p className="app-refused app-open-note">{refused}</p>}
          {refused === null && open === null && <p className="dash-quiet app-open-note">Reading…</p>}
          {open !== null && open.slug === asked && <OrgView org={open} onChanged={reread} />}
        </div>
      </div>
    </>
  );
}
