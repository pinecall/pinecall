/** An agent's Test tab: its goldens and its callers in one list, how each stood the last time, and the way to run either; one open is the side panel. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { ago } from "../lib/format";
import { Icon, type IconName } from "../shell/icons";
import { rowOfPage } from "../shell/menu";
import { useAway } from "../shell/use-away";
import { inOrder, readCallers, readRuns as readCalls, startSimulation, type PersonaRun } from "../simulations/door";
import { CallerFormPanel, CallerPanel, ProposePanel } from "./caller-panel";
import { readCases, readRun, readRuns, runGoldens, type Cases, type EvalCase, type Persona, type Run } from "./door";
import { aboutOf, goldensIn, inTheCode, isPinecalls, lastCalls, resultsOf, saidIn, setInCode, verdictOfCall, waitingIn, type Result, type Verdict } from "./fold";
import { fromOf, GoldenFormPanel, GoldenPanel, WaitingPanel } from "./golden-panel";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "./test.css";

// The turns a caller improvises before it hangs up, as Simulations' own "Normal".
const TURNS = 15;
// How long an icon that asks waits for its second click.
const FORGETS_MS = 4000;

type Filter = "all" | "goldens" | "callers" | "failing" | "waiting";

type Open =
  | { panel: "golden"; name: string }
  | { panel: "golden-form"; name: string | null }
  | { panel: "waiting"; id: string }
  | { panel: "caller"; name: string }
  | { panel: "caller-form"; name: string | null }
  | { panel: "propose" };

/** The run this page started, and the goldens it plays, until it is over. */
interface Playing {
  id: string;
  names: ReadonlySet<string>;
}

/** How it stood, in a dot and a few quiet words. */
function Status({ verdict, playing = false, children }: { verdict: Verdict | "waiting"; playing?: boolean; children?: ReactNode }): ReactNode {
  if (playing) return <span className="tst-status tst-status-playing">Playing…</span>;
  return <span className={`tst-status tst-status-${verdict}`}>{children ?? (verdict === "held" ? "Held" : verdict === "broke" ? "Broke" : "Not run")}</span>;
}

/** How many of a section stand how, as one slim bar. */
function Standing({ held, broke, none }: { held: number; broke: number; none: number }): ReactNode {
  return (
    <span className="tst-bar" role="img" aria-label={`${held} held, ${broke} broke, ${none} not run`}>
      {held > 0 && <i className="tst-bar-held" style={{ flexGrow: held }} />}
      {broke > 0 && <i className="tst-bar-broke" style={{ flexGrow: broke }} />}
      {none > 0 && <i className="tst-bar-none" style={{ flexGrow: none }} />}
    </span>
  );
}

/** A section's head: its colour and icon, what it is in a sentence, how it stands, and what it does. */
function Head({ icon, title, about, stands, said, children }: { icon: IconName; title: string; about: string; stands?: { held: number; broke: number; none: number } | undefined; said?: string | undefined; children?: ReactNode }): ReactNode {
  return (
    <header className="tst-head">
      <span className="tst-head-mark" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <span className="tst-head-words">
        <span className="tst-head-title">{title}</span>
        <span className="tst-head-about">{about}</span>
      </span>
      {said !== undefined && (
        <span className="tst-head-stands">
          {stands !== undefined && <Standing {...stands} />}
          <span>{said}</span>
        </span>
      )}
      {children}
    </header>
  );
}

function NewMenu({ callersInCode, onPick }: { callersInCode: boolean; onPick: (open: Open) => void }): ReactNode {
  const [open, setOpen] = useState(false);
  const held = useAway(open, useCallback(() => setOpen(false), []));
  const pick = (what: Open): void => {
    setOpen(false);
    onPick(what);
  };
  return (
    <div className="tst-new" ref={held}>
      <button type="button" className="app-button tst-action" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="plus" size={13} />
        New
      </button>
      {open && (
        <div className="tst-new-menu" role="menu">
          <button type="button" role="menuitem" onClick={() => pick({ panel: "golden-form", name: null })}>
            <Icon name="goldens" size={15} />
            <span>
              <b>Golden</b>
              <small>A conversation written down, and what must hold</small>
            </span>
          </button>
          {!callersInCode && (
            <>
              <button type="button" role="menuitem" onClick={() => pick({ panel: "caller-form", name: null })}>
                <Icon name="personas" size={15} />
                <span>
                  <b>Caller</b>
                  <small>Somebody a model plays against the agent</small>
                </span>
              </button>
              <button type="button" role="menuitem" onClick={() => pick({ panel: "propose" })}>
                <Icon name="bolt" size={15} />
                <span>
                  <b>Generate callers</b>
                  <small>Written for you from what the agent is</small>
                </span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function GoldenRow({ name, kept, result, playing, active, authors, onOpen, onRun }: { name: string; kept: EvalCase | null; result: Result | undefined; playing: boolean; active: boolean; authors: ReadonlyMap<string, string>; onOpen: () => void; onRun: (() => void) | null }): ReactNode {
  const said = kept === null ? "Lives in the app's code" : (saidIn(kept.golden)[0] ?? fromOf(kept, authors));
  return (
    <div className={active ? "tst-row tst-row-on" : "tst-row"}>
      <button type="button" className="tst-row-main" onClick={onOpen}>
        <span className="tst-mark" aria-hidden="true">
          <Icon name="goldens" size={14} />
        </span>
        <span className="tst-row-words">
          <span className="tst-row-name">
            <span className="dash-clip">{name}</span>
            {kept === null && <span className="tst-tag">in code</span>}
            {kept?.held_out === true && <span className="tst-tag">held out</span>}
          </span>
          <span className="tst-row-under dash-clip">{said}</span>
        </span>
        <span className="tst-row-when">{result === undefined || playing ? "" : ago(result.at)}</span>
        <Status verdict={result?.verdict ?? "none"} playing={playing} />
      </button>
      <span className="tst-row-acts">
        {onRun !== null && (
          <button type="button" className="tst-run" disabled={playing} aria-label={`Run ${name}`} title="Run it" onClick={onRun}>
            <Icon name="play" size={13} />
          </button>
        )}
      </span>
    </div>
  );
}

/** An icon that places a call: its tooltip says what it does, the first click asks, the second does it, and it forgets after a moment. */
function ConfirmIcon({ icon, tip, asks, disabled, onConfirm }: { icon: IconName; tip: string; asks: string; disabled: boolean; onConfirm: () => void }): ReactNode {
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (!asking) return;
    const timer = window.setTimeout(() => setAsking(false), FORGETS_MS);
    return () => window.clearTimeout(timer);
  }, [asking]);
  return (
    <button
      type="button"
      className={asking ? "tst-run tst-run-asking" : "tst-run"}
      disabled={disabled}
      aria-label={asking ? asks : tip}
      data-tip={asking ? asks : tip}
      onClick={() => {
        if (!asking) return setAsking(true);
        setAsking(false);
        onConfirm();
      }}
    >
      <Icon name={icon} size={13} />
    </button>
  );
}

function CallerRow({ caller, last, active, starting, onOpen, onStart }: { caller: Persona; last: PersonaRun | undefined; active: boolean; starting: boolean; onOpen: () => void; onStart: (voice: boolean) => void }): ReactNode {
  const live = last !== undefined && last.ended_at === null;
  const verdict = verdictOfCall(last);
  return (
    <div className={active ? "tst-row tst-row-on" : "tst-row"}>
      <button type="button" className="tst-row-main" onClick={onOpen}>
        <span className="tst-mark tst-mark-round" aria-hidden="true">
          {caller.name.charAt(0).toUpperCase()}
        </span>
        <span className="tst-row-words">
          <span className="tst-row-name">
            <span className="dash-clip">{caller.name}</span>
            {isPinecalls(caller) && <span className="tst-tag">Pinecall's</span>}
            {caller.tags.includes("red-team") && <span className="tst-tag">red team</span>}
          </span>
          <span className="tst-row-under dash-clip">{aboutOf(caller)}</span>
        </span>
        <span className="tst-row-when">{last === undefined || live ? "" : ago(last.started_at)}</span>
        <Status verdict={verdict} playing={live}>
          {last === undefined ? "Never called" : verdict === "none" ? "Not judged" : `${last.score?.held ?? 0}/${last.score?.judged ?? 0} held`}
        </Status>
      </button>
      <span className="tst-row-acts">
        <ConfirmIcon icon="chat" tip="Simulate in chat" asks={`Click again to start ${caller.name} in chat`} disabled={starting} onConfirm={() => onStart(false)} />
        <ConfirmIcon icon="numbers" tip="Simulate by voice" asks={`Click again to call as ${caller.name}`} disabled={starting} onConfirm={() => onStart(true)} />
      </span>
    </div>
  );
}

function WaitingRow({ kept, active, onOpen }: { kept: EvalCase; active: boolean; onOpen: () => void }): ReactNode {
  return (
    <div className={active ? "tst-row tst-row-on" : "tst-row"}>
      <button type="button" className="tst-row-main" onClick={onOpen}>
        <span className="tst-mark" aria-hidden="true">
          <Icon name="cases" size={14} />
        </span>
        <span className="tst-row-words">
          <span className="tst-row-name">
            <span className="dash-clip">{saidIn(kept.golden)[0] ?? kept.name}</span>
          </span>
          <span className="tst-row-under dash-clip">{kept.broke.map((one) => one.judge).join(", ") || kept.name}</span>
        </span>
        <span className="tst-row-when">{ago(kept.created_at)}</span>
        <Status verdict="waiting">Waiting</Status>
      </button>
      <span className="tst-row-acts" />
    </div>
  );
}

export function TestTab({ agent, kind, authors }: { agent: string; kind: "code" | "studio"; authors: ReadonlyMap<string, string> }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [listed, setListed] = useState<Cases | null>(null);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [callers, setCallers] = useState<Persona[] | null>(null);
  const [calls, setCalls] = useState<PersonaRun[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [playing, setPlaying] = useState<Playing | null>(null);
  const [starting, setStarting] = useState(false);
  const [open, setOpen] = useState<Open | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [library, setLibrary] = useState(false);
  const close = useCallback(() => setOpen(null), []);

  const said = useCallback((failed: unknown): void => setRefused(saidBy(failed)), []);
  const rereadRuns = useCallback((): void => void readRuns(credentials, agent).then(setRuns, (failed: unknown) => (setRuns((was) => was ?? []), said(failed))), [credentials, agent, said]);

  useEffect(() => {
    readCases(credentials, agent).then(setListed, (failed: unknown) => (setListed({ cases: [], pending: 0 }), said(failed)));
    readCallers(credentials, agent).then(setCallers, (failed: unknown) => (setCallers([]), said(failed)));
    readCalls(credentials, [agent]).then((read) => setCalls(read.runs), () => setCalls([]));
    rereadRuns();
  }, [credentials, agent, said, rereadRuns]);

  // The run started here is read again each time the gateway says a run changed, until it is over.
  useFed(
    () => {
      if (playing === null) return;
      readRun(credentials, playing.id).then((run) => {
        if (run.status === "running") return;
        if (run.status === "failed") setRefused(run.error ?? "The run broke before it finished.");
        setPlaying(null);
        rereadRuns();
      }, said);
    },
    { types: ["run.changed"] },
    [playing?.id],
  );

  const cases = listed?.cases ?? [];
  const goldens = useMemo(() => goldensIn(cases), [cases]);
  const waiting = useMemo(() => waitingIn(cases), [cases]);
  const results = useMemo(() => resultsOf(runs ?? []), [runs]);
  // A Studio agent has no code: a golden a run played and the gateway keeps no case of was deleted since.
  const coded = useMemo(() => (kind === "code" ? inTheCode(results, cases) : []), [kind, results, cases]);
  const last = useMemo(() => lastCalls(calls ?? []), [calls]);
  const ordered = useMemo(() => inOrder(callers ?? []), [callers]);
  const mine = ordered.filter((one) => !isPinecalls(one) || one.on);
  const shelf = ordered.filter((one) => isPinecalls(one) && !one.on);
  const callersInCode = setInCode(callers ?? []);
  const playable = goldens.filter((one) => !one.held_out).map((one) => one.name);
  const whyNoRun = goldens.length > 0 ? "Every golden is held out" : coded.length > 0 ? "These goldens live in the app's code: pinecall test plays them" : "No golden to play yet. Write one with New, or keep a waiting call";

  const run = async (names: readonly string[]): Promise<void> => {
    if (names.length === 0 || playing !== null) return;
    setRefused(null);
    try {
      const started = await runGoldens(credentials, agent, names);
      setPlaying({ id: started.id, names: new Set(names) });
    } catch (failed) {
      said(failed);
    }
  };

  // A caller started is watched on Simulations, where a call has the whole page.
  const start = async (caller: string, voice: boolean): Promise<void> => {
    setStarting(true);
    setRefused(null);
    try {
      const call = await startSimulation(credentials, { agent, persona: caller, voice, turns: TURNS });
      void navigate(`/simulations/${call}`);
    } catch (failed) {
      said(failed);
      setStarting(false);
    }
  };

  const kept = (one: EvalCase): void => setListed((was) => (was === null ? was : { cases: [one, ...was.cases.filter((each) => each.id !== one.id)], pending: was.pending }));
  const changed = (one: EvalCase): void => setListed((was) => (was === null ? was : { cases: was.cases.map((each) => (each.id === one.id ? one : each)), pending: was.cases.filter((each) => (each.id === one.id ? one : each).status === "pending").length }));
  const removed = (id: string): void => setListed((was) => (was === null ? was : { ...was, cases: was.cases.filter((each) => each.id !== id) }));

  const verdictOfGolden = (name: string): Verdict => results.get(name)?.verdict ?? "none";
  const goldenNames = [...goldens.map((one) => one.name), ...coded];
  const tally = (verdicts: readonly Verdict[]): { held: number; broke: number; none: number } => ({ held: verdicts.filter((one) => one === "held").length, broke: verdicts.filter((one) => one === "broke").length, none: verdicts.filter((one) => one === "none").length });
  const goldenTally = tally(goldenNames.map(verdictOfGolden));
  const callerTally = tally(mine.map((one) => verdictOfCall(last.get(one.name))));

  const wanted = query.trim().toLowerCase();
  const matches = (...words: readonly string[]): boolean => wanted === "" || words.some((word) => word.toLowerCase().includes(wanted));
  const failingOnly = filter === "failing";
  const shownGoldens = filter === "callers" || filter === "waiting" ? [] : goldens.filter((one) => matches(one.name, ...saidIn(one.golden)) && (!failingOnly || verdictOfGolden(one.name) === "broke"));
  const shownCoded = filter === "callers" || filter === "waiting" ? [] : coded.filter((name) => matches(name) && (!failingOnly || verdictOfGolden(name) === "broke"));
  const shownCallers = filter === "goldens" || filter === "waiting" ? [] : mine.filter((one) => matches(one.name, aboutOf(one)) && (!failingOnly || verdictOfCall(last.get(one.name)) === "broke"));
  const shownWaiting = filter === "waiting" ? waiting.filter((one) => matches(one.name, ...saidIn(one.golden))) : [];
  const shownShelf = (filter === "all" || filter === "callers") && !callersInCode ? shelf.filter((one) => matches(one.name, aboutOf(one))) : [];
  const filtered = wanted !== "" || failingOnly;
  const showsGoldens = filter === "all" || filter === "goldens" || (failingOnly && shownGoldens.length + shownCoded.length > 0);
  const showsCallers = filter === "all" || filter === "callers" || (failingOnly && shownCallers.length > 0);
  const read = listed !== null && runs !== null && callers !== null;
  const failing = goldenTally.broke + callerTally.broke;

  const FILTERS: readonly { value: Filter; name: string; count: number }[] = [
    { value: "all", name: "All", count: goldenNames.length + mine.length },
    { value: "goldens", name: "Goldens", count: goldenNames.length },
    { value: "callers", name: "Callers", count: mine.length },
    { value: "failing", name: "Failing", count: failing },
    ...(waiting.length > 0 ? [{ value: "waiting" as const, name: "Waiting", count: waiting.length }] : []),
  ];

  const openGolden = open?.panel === "golden" ? open.name : null;
  const openCase = open?.panel === "golden" ? (goldens.find((one) => one.name === open.name) ?? null) : null;
  const openCaller = open?.panel === "caller" ? ordered.find((one) => one.name === open.name) : undefined;
  const openWaiting = open?.panel === "waiting" ? waiting.find((one) => one.id === open.id) : undefined;

  return (
    <div className="tst">
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      <div className="tst-tools">
        <div className="dash-switch" role="tablist" aria-label="Show">
          {FILTERS.map((one) => (
            <button key={one.value} type="button" role="tab" aria-selected={filter === one.value} className={filter === one.value ? "dash-switch-on" : ""} onClick={() => setFilter(one.value)}>
              {one.name}
              <span className="tst-count">{one.count}</span>
            </button>
          ))}
        </div>
        <label className="tst-search">
          <Icon name="search" size={14} />
          <input aria-label="Search tests" placeholder="Search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <NewMenu callersInCode={callersInCode} onPick={setOpen} />
      </div>

      {!read && <p className="dash-quiet tst-none">Reading…</p>}

      {read && showsGoldens && (
        <section className="tst-list tst-tone-gold" aria-label="Goldens">
          <Head icon="goldens" title="Goldens" about="Conversations it must get right, replayed before a change ships." stands={goldenNames.length === 0 ? undefined : goldenTally} said={goldenNames.length === 0 ? undefined : `${goldenTally.held} of ${goldenNames.length} hold`}>
            <button type="button" className="cfg-save tst-action" disabled={playing !== null || playable.length === 0} data-tip={playing === null && playable.length === 0 ? whyNoRun : undefined} onClick={() => void run(playable)}>
              <Icon name="play" size={11} />
              {playing !== null ? "Playing…" : "Run all"}
            </button>
          </Head>
          {shownGoldens.map((one) => (
            <GoldenRow key={one.id} name={one.name} kept={one} result={results.get(one.name)} playing={playing?.names.has(one.name) === true} active={openGolden === one.name} authors={authors} onOpen={() => setOpen({ panel: "golden", name: one.name })} onRun={() => void run([one.name])} />
          ))}
          {shownCoded.map((name) => (
            <GoldenRow key={`code:${name}`} name={name} kept={null} result={results.get(name)} playing={false} active={openGolden === name} authors={authors} onOpen={() => setOpen({ panel: "golden", name })} onRun={null} />
          ))}
          {shownGoldens.length + shownCoded.length === 0 && <p className="dash-quiet tst-none">{filtered ? "None." : "No golden yet. New writes one."}</p>}
          {waiting.length > 0 && filter !== "failing" && (
            <button type="button" className="tst-foot" onClick={() => setFilter("waiting")}>
              <span className="tst-foot-dot" aria-hidden="true" />
              {waiting.length} {waiting.length === 1 ? "call" : "calls"} waiting for a decision. Keep one and it becomes a golden.
              <span className="tst-foot-go">Review</span>
            </button>
          )}
        </section>
      )}

      {read && showsCallers && (
        <section className="tst-list tst-tone-blue" aria-label="Callers">
          <Head icon="personas" title="Callers" about="People a model plays against the agent, judged when they hang up." stands={mine.length === 0 ? undefined : callerTally} said={mine.length === 0 ? undefined : `${callerTally.held} of ${mine.length} passed`}>
            <Link to={`/simulations?agent=${encodeURIComponent(agent)}`} className="app-button tst-action">
              {rowOfPage("/simulations")?.name}
            </Link>
          </Head>
          {shownCallers.map((one) => (
            <CallerRow key={`${one.owner}/${one.name}`} caller={one} last={last.get(one.name)} active={openCaller?.name === one.name} starting={starting} onOpen={() => setOpen({ panel: "caller", name: one.name })} onStart={(voice) => void start(one.name, voice)} />
          ))}
          {shownCallers.length === 0 && <p className="dash-quiet tst-none">{filtered ? "None." : "No caller yet. New writes one, or add one from the library."}</p>}
          {shownShelf.length > 0 && (
            <>
              <button type="button" className="tst-shelf" aria-expanded={library} onClick={() => setLibrary(!library)}>
                <Icon name="chevron" size={14} />
                Pinecall's library
                <span className="dash-quiet">{shownShelf.length} more</span>
              </button>
              {library && shownShelf.map((one) => <CallerRow key={`shelf/${one.name}`} caller={one} last={last.get(one.name)} active={openCaller?.name === one.name} starting={starting} onOpen={() => setOpen({ panel: "caller", name: one.name })} onStart={(voice) => void start(one.name, voice)} />)}
            </>
          )}
        </section>
      )}

      {read && failingOnly && !showsGoldens && !showsCallers && <p className="dash-quiet tst-none">Nothing is failing.</p>}

      {read && filter === "waiting" && (
        <section className="tst-list tst-tone-gold" aria-label="Waiting">
          <Head icon="cases" title="Waiting for a decision" about="Calls a judge broke on. Keep one and it becomes a golden." />
          {shownWaiting.map((one) => (
            <WaitingRow key={one.id} kept={one} active={openWaiting?.id === one.id} onOpen={() => setOpen({ panel: "waiting", id: one.id })} />
          ))}
          {shownWaiting.length === 0 && <p className="dash-quiet tst-none">None.</p>}
        </section>
      )}

      {open?.panel === "golden" && (
        <GoldenPanel
          key={open.name}
          name={open.name}
          kept={openCase}
          authors={authors}
          result={results.get(open.name)}
          playing={playing?.names.has(open.name) === true}
          busy={playing !== null}
          onRun={() => void run([open.name])}
          onEdit={() => setOpen({ panel: "golden-form", name: open.name })}
          onChanged={changed}
          onRemoved={() => (openCase !== null && removed(openCase.id), close())}
          onClose={close}
        />
      )}
      {open?.panel === "golden-form" && (
        <GoldenFormPanel
          key={open.name ?? "new"}
          agent={agent}
          was={goldens.find((one) => one.name === open.name)}
          onSaved={(one) => {
            kept(one);
            setOpen({ panel: "golden", name: one.name });
          }}
          onClose={close}
        />
      )}
      {openWaiting !== undefined && (
        <WaitingPanel
          key={openWaiting.id}
          kept={openWaiting}
          authors={authors}
          onDecided={(one) => {
            changed(one);
            setOpen(one.status === "approved" ? { panel: "golden", name: one.name } : null);
          }}
          onClose={close}
        />
      )}
      {openCaller !== undefined && (
        <CallerPanel
          key={openCaller.name}
          agent={agent}
          caller={openCaller}
          last={last.get(openCaller.name)}
          starting={starting}
          onStart={(voice) => void start(openCaller.name, voice)}
          onEdit={() => setOpen({ panel: "caller-form", name: openCaller.name })}
          onCallers={(now, gone) => {
            setCallers(now);
            if (gone) close();
          }}
          onClose={close}
        />
      )}
      {open?.panel === "caller-form" && (
        <CallerFormPanel
          key={open.name ?? "new"}
          agent={agent}
          was={ordered.find((one) => one.name === open.name)}
          onSaved={(now, name) => {
            setCallers(now);
            setOpen({ panel: "caller", name });
          }}
          onClose={close}
        />
      )}
      {open?.panel === "propose" && <ProposePanel agent={agent} taken={new Set(ordered.filter((one) => !isPinecalls(one)).map((one) => one.name))} onKept={setCallers} onClose={close} />}
    </div>
  );
}
