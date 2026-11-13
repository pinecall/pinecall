/** Apps and Agents, one page twice: the list beside the one open, its head and its tabs; what is written as code on one, what is built in Studio on the other. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, useNavigate, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readMembers } from "@pinecall/core/members";
import { AdvancedTab } from "../advanced/advanced";
import { Configure } from "../configure/configure";
import { KnowledgeTab } from "../configure/knowledge";
import { StudioTools } from "../configure/tools";
import { useOrg } from "../lib/org";
import { inWorld, WORLD } from "../lib/world";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { useAway } from "../shell/use-away";
import { AppOverview } from "./app";
import { Avatar } from "./avatar";
import { ConfirmButton } from "./confirm";
import { readHosted, readServed, removeApp, startApp, stopApp, type Hosted } from "./door";
import { appsOf, isOfAgents, saidOf, type App } from "./fold";
import { LogsCard } from "./logs";
import { Releases } from "./releases";
import { Secrets } from "./secrets";
import { Setup } from "./setup";
import { TalkButton, TalkPanel } from "../talk/talk-panel";
import { TestTab } from "../test/test";
import { ChannelsTab } from "../channels/channels";
import { MonitorsBoard } from "../monitors/board";
import { NewAgentPanel } from "./new-agent";
import { isAnswering, NEEDS_IT_ANSWERING, NotAnswering } from "./not-answering";
import { deployStudioAgent } from "./studio-door";
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
    { path: "channels", name: "Channels", icon: "numbers" },
    { path: "test", name: "Test", icon: "cases" },
    { path: "monitors", name: "Monitors", icon: "monitors" },
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
    { path: "channels", name: "Channels", icon: "numbers" },
    { path: "test", name: "Test", icon: "cases" },
    { path: "monitors", name: "Monitors", icon: "monitors" },
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

/** A row opens its agent on the tab already open, so going down the list compares the same page of each. */
function Row({ app, kind, base, tab }: { app: App; kind: Kind["kind"]; base: string; tab: string }): ReactNode {
  const said = saidOf(app);
  return (
    <NavLink to={`${base}/${encodeURIComponent(app.name)}${tab === "" ? "" : `/${tab}`}`} className={({ isActive }) => `app-row app-row-worn${app.of === null ? "" : " app-row-of"}${isActive ? " app-row-on" : ""}`}>
      <Avatar kind={kind} name={app.name} size={app.of === null ? 32 : 24} />
      <span className="app-row-words">
        <span className="app-row-top">
          <span className="dash-clip">{app.name}</span>
          <span className={`app-dot app-dot-${said.mood}`} aria-hidden="true" />
        </span>
        <span className="app-row-under dash-clip">{said.state}</span>
      </span>
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
  const [deployed, setDeployed] = useState<number | null>(null);
  const { hosted, name } = app;
  const act = async (doing: () => Promise<void>, then: () => void): Promise<void> => {
    setRefused(null);
    setDeployed(null);
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
      {deployed !== null && <span className="app-said">Release {deployed} answers in production</span>}
      {/* A Studio agent is built in the sandbox; this is how what was built reaches production. */}
      {hosted.kind === "studio" && WORLD === "sandbox" && hosted.release !== null && !hosted.stopped && (
        <ConfirmButton label="Deploy" asks={`Send release ${hosted.release} to production?`} onConfirm={() => void act(() => deployStudioAgent(credentials, name, hosted.release ?? 0), () => setDeployed(hosted.release))} />
      )}
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

const NEW_UNDER = "pinecall.new-agent";

// The word is kept for the tab alone, and for one page load: a browser that keeps nothing just opens the list.
function wantsNew(): boolean {
  try {
    return window.sessionStorage.getItem(NEW_UNDER) === "1";
  } catch {
    return false;
  }
}

function wantNew(wanted: boolean): void {
  try {
    if (wanted) window.sessionStorage.setItem(NEW_UNDER, "1");
    else window.sessionStorage.removeItem(NEW_UNDER);
  } catch {
    // Nothing is kept.
  }
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
  // Production's button leaves a word for the sandbox's page, which opens on the form.
  const [making, setMaking] = useState(() => kind === "studio" && WORLD === "sandbox" && wantsNew());
  const makes = kind === "studio";
  // An agent is made in Studio, in the sandbox, and reaches production by a deploy: production's button opens the sandbox on the form.
  const make = (): void => {
    if (WORLD === "sandbox") return setMaking(true);
    wantNew(true);
    window.location.assign(inWorld("sandbox", base));
  };
  useEffect(() => wantNew(false), []);
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
  // An app's agent has no releases of its own, and an app of several agents has no settings, channels or tests of its own.
  const shownTabs = open === undefined ? tabs : open.of !== null ? tabs.filter((one) => one.path !== "releases") : isOfAgents(open) ? tabs.filter((one) => one.path === "" || one.path === "releases") : tabs;
  const at = shownTabs.some((one) => one.path === tab) ? tab : undefined;

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (read && asked === undefined && apps[0] !== undefined) return <Navigate to={`${base}/${encodeURIComponent(apps[0].name)}`} replace />;

  const leave = (): void => {
    reread();
    void navigate(base, { replace: true });
  };

  return (
    <>
      <PageHead open={open?.name} mark={open !== undefined && <Avatar kind={kind} name={open.name} size={20} />}>
        {open !== undefined && (
          <>
            {!isOfAgents(open) && <TalkButton open={talking} onClick={() => setTalking(!talking)} />}
            <Actions key={open.name} app={open} onChanged={reread} onRemoved={leave} />
          </>
        )}
      </PageHead>
      {open !== undefined && talking && !making && !isOfAgents(open) && <TalkPanel agent={open.agent} onClose={stopTalking} />}
      {making && (
        <NewAgentPanel
          taken={new Set(agents.map((one) => one.slug))}
          onMade={reread}
          onOpen={(name, talk) => {
            setMaking(false);
            reread();
            setTalking(talk);
            void navigate(`${base}/${encodeURIComponent(name)}${talk ? "" : "/configure"}`);
          }}
          onClose={() => setMaking(false)}
        />
      )}
      <div className="app-layout">
        <aside className="app-list" aria-label={title}>
          <div className="app-list-head">
            <span className="app-list-title">{title}</span>
            <span className="dash-quiet">{read ? apps.filter((one) => one.of === null).length : ""}</span>
            {makes && (
              <button type="button" className="app-button app-list-new" title={WORLD === "sandbox" ? "New agent" : "Agents are built in the sandbox: this opens it"} onClick={make}>
                New
              </button>
            )}
          </div>
          <input className="app-input app-search" aria-label={search} placeholder={search} value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {shown.map((one) => (
              <Row key={one.name} app={one} kind={kind} base={base} tab={tabs.some((each) => each.path === tab) ? (tab ?? "") : ""} />
            ))}
            {read && apps.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
        </aside>
        <div className="app-open">
          {refused !== null && <p className="app-refused app-open-note">{refused}</p>}
          {!read && <p className="dash-quiet app-open-note">Reading…</p>}
          {read && open === undefined && (
            <div className="app-open-note">
              {nothing}
              {makes && (
                <p className="app-note">
                  <button type="button" className="cfg-save" onClick={make}>
                    New agent
                  </button>
                </p>
              )}
            </div>
          )}
          {open !== undefined && (
            <>
              <Tabs name={open.name} base={base} tabs={shownTabs}>
              </Tabs>
              <div className="app-main">
                {/* A tab that reads the agent as it runs is drawn only while the gateway answers for it. */}
                {at !== undefined && NEEDS_IT_ANSWERING.has(at) && !isAnswering(open) && agentsRead ? (
                  <NotAnswering key={open.name} app={open} base={base} onChanged={reread} onRemoved={leave} />
                ) : (
                  <>
                    {kind === "studio" && at === "configure" && <Configure key={open.name} agent={open.agent} kind={kind} onSaved={reread} />}
                    {kind === "studio" && at === "knowledge" && <KnowledgeTab key={open.name} agent={open.agent} />}
                    {kind === "studio" && at === "tools" && <StudioTools key={open.name} agent={open.agent} onSaved={reread} />}
                    {kind === "studio" && at === "advanced" && <AdvancedTab key={open.name} agent={open.agent} kind={kind} />}
                    {at === "channels" && <ChannelsTab key={open.name} agent={open.agent} />}
                    {at === "monitors" && <MonitorsBoard key={open.name} agent={open.agent} />}
                    {at === "test" && <TestTab key={open.name} agent={open.agent} kind={kind} authors={names} />}
                    {kind === "code" && at === "setup" && <Setup key={open.name} agent={open.agent} />}
                    {kind === "code" && at === "releases" && <ReleasesTab key={open.name} app={open} names={names} onChanged={reread} />}
                  </>
                )}
                {(at === undefined || at === "") && <AppOverview key={open.name} app={open} kind={kind} base={base} served={served.get(open.name) ?? 0} names={names} onChanged={reread} />}
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
