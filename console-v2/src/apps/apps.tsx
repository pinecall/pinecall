/** Apps and Agents, one page twice: the list beside the one open, its head and its tabs; what is written as code on one, what is built in Studio on the other. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, useNavigate, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readMembers } from "@pinecall/core/members";
import { AdvancedTab } from "../advanced/advanced";
import { Configure } from "../configure/configure";
import { ReadOnlyNote, readOnlyFor } from "../configure/corner";
import { KnowledgeTab } from "../configure/knowledge";
import { StudioTools } from "../configure/tools";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { useAway } from "../shell/use-away";
import { AppOverview } from "./app";
import { ConfirmButton } from "./confirm";
import { readHosted, readServed, removeApp, startApp, stopApp, type Hosted } from "./door";
import { appsOf, saidOf, type App } from "./fold";
import { LogsCard } from "./logs";
import { Releases } from "./releases";
import { Secrets } from "./secrets";
import { Setup } from "./setup";
import { TalkButton, TalkPanel } from "../talk/talk-panel";
import "../dashboard/dashboard.css";
import "./apps.css";

const DEPLOY = WORLD === "production" ? "pinecall deploy --prod" : "pinecall deploy";

interface Tab {
  path: string;
  name: string;
  icon: IconName;
}

interface Kind {
  kind: "code" | "studio";
  tabs: readonly Tab[];
  base: string;
  title: string;
  search: string;
  nothing: ReactNode;
}

const APPS: Kind = {
  kind: "code",
  tabs: [
    { path: "", name: "Overview", icon: "dashboard" },
    { path: "setup", name: "Setup", icon: "settings" },
    { path: "releases", name: "Releases", icon: "releases" },
  ],
  base: "/apps",
  title: "Apps",
  search: "Search apps",
  nothing: (
    <div className="app-empty">
      <h2 className="app-name">No app here yet</h2>
      <p className="dash-quiet">An app is an agent written as code. Run this in its folder and Pinecall keeps it running for you, or connect it from a server of your own.</p>
      <code className="app-command">{DEPLOY}</code>
    </div>
  ),
};

const AGENTS: Kind = {
  kind: "studio",
  tabs: [
    { path: "", name: "Overview", icon: "dashboard" },
    { path: "configure", name: "Configure", icon: "settings" },
    { path: "knowledge", name: "Knowledge", icon: "knowledge" },
    { path: "tools", name: "Tools", icon: "tools" },
    { path: "advanced", name: "Advanced", icon: "gauge" },
  ],
  base: "/agents",
  title: "Agents",
  search: "Search agents",
  nothing: (
    <div className="app-empty">
      <h2 className="app-name">No agent here yet</h2>
      <p className="dash-quiet">An agent is built in Studio, with no code. The ones you build show up here.</p>
    </div>
  ),
};

function Row({ app, base }: { app: App; base: string }): ReactNode {
  const said = saidOf(app);
  return (
    <NavLink to={`${base}/${encodeURIComponent(app.name)}`} className={({ isActive }) => (isActive ? "app-row app-row-on" : "app-row")}>
      <span className="app-row-top">
        <span className="dash-clip">{app.name}</span>
        <span className={`app-dot app-dot-${said.mood}`} aria-hidden="true" />
      </span>
      <span className="app-row-under dash-clip">{said.state}</span>
    </NavLink>
  );
}

export function More({ children }: { children: ReactNode }): ReactNode {
  const [open, setOpen] = useState(false);
  const held = useAway(open, useCallback(() => setOpen(false), []));
  return (
    <div className="app-more" ref={held}>
      <button type="button" className="app-button app-button-icon" aria-label="More" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="more" size={15} />
      </button>
      {open && (
        <div className="app-more-menu" role="menu">
          {children}
        </div>
      )}
    </div>
  );
}

function Actions({ app, onChanged, onRemoved }: { app: App; onChanged: () => void; onRemoved: () => void }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const { hosted, name } = app;
  const act = async (doing: () => Promise<void>, then: () => void): Promise<void> => {
    setRefused(null);
    try {
      await doing();
      then();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };
  if (hosted === null) return null;
  return (
    <div className="app-actions">
      {refused !== null && <span className="app-refused">{refused}</span>}
      {hosted.stopped ? (
        <button type="button" className="app-button" onClick={() => void act(() => startApp(credentials, name), onChanged)}>
          Start
        </button>
      ) : (
        <ConfirmButton label="Stop" asks="Stop it?" onConfirm={() => void act(() => stopApp(credentials, name), onChanged)} />
      )}
      <More>
        <ConfirmButton label="Remove" asks="Remove for good?" danger onConfirm={() => void act(() => removeApp(credentials, name), onRemoved)} />
      </More>
    </div>
  );
}

function Tabs({ name, base, tabs, children }: { name: string; base: string; tabs: readonly Tab[]; children?: ReactNode }): ReactNode {
  const at = `${base}/${encodeURIComponent(name)}`;
  return (
    <nav className="app-tabs" aria-label={`${name}'s pages`}>
      {tabs.map((tab) => (
        <NavLink key={tab.path} to={tab.path === "" ? at : `${at}/${tab.path}`} end className={({ isActive }) => (isActive ? "app-tab app-tab-on" : "app-tab")}>
          <Icon name={tab.icon} size={15} />
          {tab.name}
        </NavLink>
      ))}
      {children}
    </nav>
  );
}

/** Where Pinecall runs the app: its releases and their logs; and the secrets its code reads. */
function ReleasesTab({ app, names, onChanged }: { app: App; names: ReadonlyMap<string, string>; onChanged: () => void }): ReactNode {
  const { hosted, name } = app;
  return (
    <div className="app-panel">
      {hosted !== null && <Releases key={`${name}:${hosted.release ?? 0}`} app={hosted} names={names} onRolledBack={onChanged} />}
      {hosted !== null && <LogsCard key={name} name={name} />}
      {hosted === null && <p className="dash-quiet app-note">This app runs on a server of yours, so its releases and logs live there. Run pinecall deploy from its folder and Pinecall keeps it running for you, with releases you can roll back.</p>}
      <Secrets names={names} />
    </div>
  );
}

function Fleet({ kind, tabs, base, title, search, nothing }: Kind): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const { agents, agentsRead } = useOrg();
  const { app: asked, tab } = useParams();
  const [hosted, setHosted] = useState<Hosted[] | null>(null);
  const [served, setServed] = useState<ReadonlyMap<string, number>>(new Map());
  const [refused, setRefused] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  const [talking, setTalking] = useState(false);
  const stopTalking = useCallback(() => setTalking(false), []);

  const reread = useCallback((): void => {
    readHosted(credentials).then(setHosted, (failed: unknown) => {
      setHosted([]);
      setRefused(saidBy(failed));
    });
    readServed(credentials).then(setServed, () => undefined);
  }, [credentials]);

  useEffect(reread, [reread]);

  // A key that may not list the team still sees its apps, with "A teammate" for who deployed them.
  useEffect(() => {
    readMembers(credentials).then((members) => setNames(new Map(members.map((one) => [one.id, one.name]))), () => undefined);
  }, [credentials]);

  const apps = useMemo(() => appsOf(hosted ?? [], agents, kind), [hosted, agents, kind]);
  const shown = apps.filter((one) => one.name.toLowerCase().includes(filter.trim().toLowerCase()));
  const read = hosted !== null && agentsRead;
  const open = apps.find((one) => one.name === asked) ?? apps[0];

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (read && asked === undefined && apps[0] !== undefined) return <Navigate to={`${base}/${encodeURIComponent(apps[0].name)}`} replace />;

  const leave = (): void => {
    reread();
    void navigate(base, { replace: true });
  };

  return (
    <>
      <PageHead open={open?.name}>
        {open !== undefined && (
          <>
            <TalkButton open={talking} onClick={() => setTalking(!talking)} />
            <Actions key={open.name} app={open} onChanged={reread} onRemoved={leave} />
          </>
        )}
      </PageHead>
      {open !== undefined && talking && <TalkPanel agent={open.name} onClose={stopTalking} />}
      <div className="app-layout">
        <aside className="app-list" aria-label={title}>
          <div className="app-list-head">
            <span className="app-list-title">{title}</span>
            <span className="dash-quiet">{read ? apps.length : ""}</span>
          </div>
          <input className="app-input app-search" aria-label={search} placeholder={search} value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {shown.map((one) => (
              <Row key={one.name} app={one} base={base} />
            ))}
            {read && apps.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
        </aside>
        <div className="app-open">
          {refused !== null && <p className="app-refused app-open-note">{refused}</p>}
          {!read && <p className="dash-quiet app-open-note">Reading…</p>}
          {read && open === undefined && <div className="app-open-note">{nothing}</div>}
          {open !== undefined && (
            <>
              <Tabs name={open.name} base={base} tabs={tabs}>
                {readOnlyFor(kind) && (tab === "setup" || tab === "configure" || tab === "knowledge" || tab === "tools" || tab === "advanced") && <ReadOnlyNote kind={kind} />}
              </Tabs>
              <div className="app-main">
                {kind === "studio" && tab === "configure" && <Configure key={open.name} agent={open.name} kind={kind} onSaved={reread} />}
                {kind === "studio" && tab === "knowledge" && <KnowledgeTab key={open.name} agent={open.name} kind={kind} />}
                {kind === "studio" && tab === "tools" && <StudioTools key={open.name} agent={open.name} kind={kind} onSaved={reread} />}
                {kind === "studio" && tab === "advanced" && <AdvancedTab key={open.name} agent={open.name} kind={kind} />}
                {kind === "code" && tab === "setup" && <Setup key={open.name} agent={open.name} />}
                {kind === "code" && tab === "releases" && <ReleasesTab key={open.name} app={open} names={names} onChanged={reread} />}
                {!tabs.some((one) => one.path === tab && one.path !== "") && <AppOverview key={open.name} app={open} kind={kind} served={served.get(open.name) ?? 0} names={names} onChanged={reread} />}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

export function AppsPage(): ReactNode {
  return <Fleet {...APPS} />;
}

export function AgentsPage(): ReactNode {
  return <Fleet {...AGENTS} />;
}
