/** Knowledge, the same page as Apps and Agents: the org's bases in a list beside the one open, and what its agents remember at the list's foot. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Navigate, NavLink, useNavigate, useParams, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { More } from "../apps/apps";
import { ConfirmButton } from "../apps/confirm";
import { NewBase } from "../configure/new-base";
import { ago } from "../lib/format";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { SidePanel } from "../ui/side-panel";
import { BaseView } from "./base";
import { chunksIn, dropBase, readBases, type BaseRead } from "./door";
import { MemoryView } from "./memory";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "../configure/knowledge.css";
import "./knowledge.css";

const HOME = "/knowledge";
const NEW_BASE = "new-base";
const baseAt = (base: string): string => `${HOME}/bases/${encodeURIComponent(base)}`;
const rowClass = ({ isActive }: { isActive: boolean }): string => (isActive ? "app-row app-row-on" : "app-row");

function Row({ base }: { base: BaseRead }): ReactNode {
  const used = base.agents.length > 0;
  return (
    <NavLink to={baseAt(base.base)} className={rowClass}>
      <span className="app-row-top">
        <span className="dash-clip">{base.base}</span>
        <span className={used ? "app-dot app-dot-good" : "app-dot app-dot-calm"} title={used ? "An agent searches it" : "No agent searches it yet"} aria-hidden="true" />
      </span>
      <span className="app-row-under dash-clip">
        {chunksIn(base.chunks)}, {ago(base.pushed_at)}
      </span>
    </NavLink>
  );
}

function Actions({ base, onRemoved }: { base: string; onRemoved: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const remove = async (): Promise<void> => {
    setRefused(null);
    try {
      await dropBase(credentials, base);
      await onRemoved();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };
  return (
    <div className="app-actions">
      {refused !== null && <span className="app-refused">{refused}</span>}
      <More>
        <ConfirmButton label="Remove base" asks="Remove for good?" danger onConfirm={() => void remove()} />
      </More>
    </div>
  );
}

export function KnowledgePage({ memory = false }: { memory?: boolean }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const { base: asked } = useParams();
  const [params, setParams] = useSearchParams();
  const making = params.get("panel") === NEW_BASE;
  const [bases, setBases] = useState<BaseRead[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const reread = useCallback(async (): Promise<void> => {
    try {
      setBases(await readBases(credentials));
      setRefused(null);
    } catch (failed) {
      setBases((was) => was ?? []);
      setRefused(saidBy(failed));
    }
  }, [credentials]);

  useEffect(() => {
    void reread();
  }, [reread]);

  const open = bases?.find((one) => one.base === asked);
  const first = bases?.[0];

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (!memory && open === undefined && first !== undefined) return <Navigate to={baseAt(first.base)} replace />;

  const leave = async (): Promise<void> => {
    await reread();
    void navigate(HOME, { replace: true });
  };

  // Read again before going there: an address the list does not hold yet goes back to the first.
  const made = async (name: string): Promise<void> => {
    await reread();
    void navigate(baseAt(name));
  };

  const typed = filter.trim().toLowerCase();
  const shown = (bases ?? []).filter((one) => one.base.includes(typed));
  const closeMaking = (): void => setParams({});

  return (
    <>
      <PageHead open={memory ? "Memory" : open?.base}>{!memory && open !== undefined && <Actions key={open.base} base={open.base} onRemoved={leave} />}</PageHead>
      <div className="app-layout kb-layout">
        <aside className="app-list" aria-label="Knowledge">
          <div className="app-list-head">
            <span className="app-list-title">Knowledge</span>
            <span className="dash-quiet">{bases === null ? "" : bases.length}</span>
            <button type="button" className="app-button kb-new" onClick={() => setParams({ panel: NEW_BASE })}>
              New
            </button>
          </div>
          <input className="app-input app-search" aria-label="Search bases" placeholder="Search bases" value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {shown.map((one) => (
              <Row key={one.base} base={one} />
            ))}
            {bases !== null && bases.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
          <div className="kb-foot">
            <NavLink to={`${HOME}/memory`} className={rowClass}>
              <span className="kb-memory-name">
                <Icon name="brain" size={14} />
                Memory
              </span>
              <span className="app-row-under dash-clip">What the agents remember of a caller</span>
            </NavLink>
          </div>
        </aside>
        <div className="app-open">
          {refused !== null && <p className="app-refused app-open-note">{refused}</p>}
          {bases === null && !memory && <p className="dash-quiet app-open-note">Reading…</p>}
          {bases !== null && !memory && open === undefined && (
            <div className="app-open-note">
              <div className="app-empty">
                <h2 className="app-name">No knowledge base here yet</h2>
                <p className="dash-quiet">A knowledge base is the documents an agent can search while it talks. Create one here with New, or push a folder from a project.</p>
                <code className="app-command">pinecall docs push --base my-docs</code>
              </div>
            </div>
          )}
          {(memory || open !== undefined) && <div className="app-main">{memory ? <MemoryView /> : open !== undefined && <BaseView key={open.base} base={open} onChanged={reread} onEmptied={leave} />}</div>}
        </div>
      </div>
      {making && (
        <SidePanel title="New knowledge base" icon="knowledge" about="A name and its first documents. Turn it on for an agent in that agent's Knowledge tab." onClose={closeMaking}>
          <NewBase taken={(bases ?? []).map((one) => one.base)} using={false} onMade={(name) => void made(name)} onCancel={closeMaking} />
        </SidePanel>
      )}
    </>
  );
}
