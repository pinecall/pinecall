/** Goldens: every golden of every agent of the org in one list, grouped by agent, with how each stood the last time; the one open is the Test tab's own side panel. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readMembers } from "@pinecall/core/members";
import { useFed } from "@pinecall/core/use-fed";
import { readHosted, type Hosted } from "../apps/door";
import { useOrg } from "../lib/org";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { readRun, runGoldens, type EvalCase } from "../test/door";
import { GoldenFormPanel, GoldenPanel } from "../test/golden-panel";
import { AgentPick } from "../ui/agent-pick";
import { agentsOf, goldenPath, rowsOf, shownOf, tallyOf, type Filter, type Row } from "./fold";
import { Group } from "./group";
import { Hero } from "./hero";
import { useReads } from "./reads";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
// The panels reused from the Test tab are drawn with its classes.
import "../test/test.css";
import "./goldens.css";

const AGENT = "agent";

const FILTERS: readonly { value: Filter; name: string }[] = [
  { value: "all", name: "All" },
  { value: "broke", name: "Broke" },
  { value: "none", name: "Not run" },
];

/** The run this page started, whose agent's, and the goldens it plays, until it is over. */
interface Playing {
  id: string;
  agent: string;
  names: ReadonlySet<string>;
}

/** The address says whose goldens (`?agent=`) and which one is open (`/goldens/<agent>/<golden>`). */
export function GoldensPage(): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const { search } = useLocation();
  const { agent: openAgent, golden: openName } = useParams();
  const [params, setParams] = useSearchParams();
  const picked = params.get(AGENT) ?? "";
  const { agents: held, agentsRead } = useOrg();
  const [hosted, setHosted] = useState<Hosted[] | null>(null);
  const [authors, setAuthors] = useState<ReadonlyMap<string, string>>(new Map());
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [form, setForm] = useState<{ agent: string; name: string | null } | null>(null);
  const [playing, setPlaying] = useState<Playing | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    readHosted(credentials).then(setHosted, () => setHosted([]));
    // A key that may not list the team still sees the goldens, written by "a teammate".
    readMembers(credentials).then((members) => setAuthors(new Map(members.map((one) => [one.id, one.name]))), () => undefined);
  }, [credentials]);

  const listed = agentsRead && hosted !== null;
  const agents = useMemo(() => (listed ? agentsOf(held, hosted, picked) : []), [listed, held, hosted, picked]);
  const inView = useMemo(() => (picked === "" ? agents : agents.filter((one) => one.slug === picked)), [agents, picked]);
  const { read, changeCases, rereadRuns } = useReads(useMemo(() => inView.map((one) => one.slug), [inView]));

  const groups = useMemo(
    () =>
      inView.map((agent) => {
        const got = read.get(agent.slug);
        return { agent, refused: got?.refused ?? null, rows: got === undefined ? null : rowsOf(agent, got) };
      }),
    [inView, read],
  );

  // The run started here is read again each time the gateway says a run changed, until it is over.
  useFed(
    () => {
      if (playing === null) return;
      readRun(credentials, playing.id).then(
        (run) => {
          if (run.status === "running") return;
          if (run.status === "failed") setRefused(run.error ?? "The run broke before it finished.");
          setPlaying(null);
          rereadRuns(playing.agent);
        },
        (failed: unknown) => setRefused(saidBy(failed)),
      );
    },
    { types: ["run.changed"] },
    [playing?.id],
  );

  const run = async (agent: string, names: readonly string[]): Promise<void> => {
    if (names.length === 0 || playing !== null) return;
    setRefused(null);
    try {
      const started = await runGoldens(credentials, agent, names);
      setPlaying({ id: started.id, agent, names: new Set(names) });
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const pick = useCallback(
    (agent: string): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          if (agent === "") next.delete(AGENT);
          else next.set(AGENT, agent);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const close = useCallback((): void => void navigate(`/goldens${search}`), [navigate, search]);
  const closeForm = useCallback((): void => setForm(null), []);

  const everyRow = groups.flatMap((group): readonly Row[] => group.rows ?? []);
  const tally = tallyOf(everyRow);
  const reading = groups.filter((group) => group.rows === null).length;
  const without = groups.filter((group) => group.rows !== null && group.rows.length === 0).length;
  const filtered = filter !== "all" || query.trim() !== "";
  const drawn = groups.map((group) => ({ ...group, shown: group.rows === null ? [] : shownOf(group.rows, filter, query) }));
  // Searched or filtered, an agent with nothing to show steps aside; one still being read stays.
  const visible = filtered ? drawn.filter((group) => group.rows === null || group.shown.length > 0) : drawn;

  const openGroup = groups.find((group) => group.agent.slug === openAgent);
  const openRow = openGroup?.rows?.find((row) => row.name === openName);
  const formWas = form === null || form.name === null ? undefined : groups.find((group) => group.agent.slug === form.agent)?.rows?.find((row) => row.name === form.name)?.kept ?? undefined;

  return (
    <>
      <PageHead open={openRow?.name}>
        <AgentPick agent={picked} onPick={pick} />
      </PageHead>
      <div className="gd">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}
        {!listed && <p className="dash-quiet">Reading the agents…</p>}
        {listed && inView.length === 0 && (
          <section className="dash-card gd-none" aria-label="No agent">
            <p className="gd-none-words">
              There is no agent here yet, and a golden is a conversation one of them must get right: make one under <Link to="/agents">Agents</Link> or deploy one under <Link to="/apps">Apps</Link>.
            </p>
          </section>
        )}
        {listed && inView.length > 0 && (
          <>
            {reading === 0 && everyRow.length === 0 ? (
              <section className="dash-card gd-none" aria-label="No golden">
                <p className="gd-none-words">No golden is written yet: New, under an agent, writes down a conversation it must get right, and Run plays it again before a change ships.</p>
              </section>
            ) : (
              <Hero tally={tally} agents={inView.length} without={without} reading={reading} />
            )}
            <div className="gd-tools">
              <div className="dash-switch" role="tablist" aria-label="Show">
                {FILTERS.map((one) => (
                  <button key={one.value} type="button" role="tab" aria-selected={filter === one.value} className={filter === one.value ? "dash-switch-on" : ""} onClick={() => setFilter(one.value)}>
                    {one.name}
                  </button>
                ))}
              </div>
              <label className="gd-search">
                <Icon name="search" size={14} />
                <input aria-label="Search goldens" placeholder="Search goldens" value={query} onChange={(event) => setQuery(event.target.value)} />
              </label>
            </div>
            {visible.map((group) => (
              <Group
                key={group.agent.slug}
                agent={group.agent}
                rows={group.rows}
                shown={group.shown}
                filtered={filtered}
                refused={group.refused}
                search={search}
                open={openAgent === group.agent.slug ? (openName ?? null) : null}
                playing={playing?.agent === group.agent.slug ? playing.names : null}
                busy={playing !== null}
                authors={authors}
                onRun={(names) => void run(group.agent.slug, names)}
                onNew={() => setForm({ agent: group.agent.slug, name: null })}
              />
            ))}
            {filtered && visible.length === 0 && <p className="dash-quiet gd-quiet">{filter === "broke" && query.trim() === "" ? "Nothing broke in its last run." : "No golden matches."}</p>}
          </>
        )}
      </div>
      {form === null && openRow !== undefined && openAgent !== undefined && (
        <GoldenPanel
          key={`${openAgent}/${openRow.name}`}
          name={openRow.name}
          kept={openRow.kept}
          authors={authors}
          result={openRow.result}
          playing={playing?.agent === openAgent && playing.names.has(openRow.name)}
          busy={playing !== null}
          onRun={() => void run(openAgent, [openRow.name])}
          onEdit={() => setForm({ agent: openAgent, name: openRow.name })}
          onChanged={(one: EvalCase) => changeCases(openAgent, (was) => was.map((each) => (each.id === one.id ? one : each)))}
          onRemoved={() => {
            const gone = openRow.kept?.id;
            changeCases(openAgent, (was) => was.filter((each) => each.id !== gone));
            close();
          }}
          onClose={close}
        />
      )}
      {form !== null && (
        <GoldenFormPanel
          key={`${form.agent}/${form.name ?? "new"}`}
          agent={form.agent}
          was={formWas}
          onSaved={(one) => {
            changeCases(form.agent, (was) => [one, ...was.filter((each) => each.id !== one.id)]);
            setForm(null);
            void navigate(`${goldenPath(form.agent, one.name)}${search}`);
          }}
          onClose={closeForm}
        />
      )}
    </>
  );
}
