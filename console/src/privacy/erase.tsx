/** The export and erase tab: the environment downloaded whole, a contact or one call erased for good, and the trail every erasure leaves. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { WORLD } from "../lib/world";
import { Copy, useMove } from "../numbers/parts";
import { Icon, type IconName } from "../shell/icons";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { eraseCall, eraseContact, exportWorld, readTrail, type Erasure } from "./door";
import { dayAndTime, Head, many, whoOf, type Names } from "./parts";

// How many erasures the trail draws before it offers the rest.
const A_FEW = 15;

type Kind = "contact" | "call";
type Open = { panel: Kind } | { panel: "erasure"; id: number };

const ERASES: Record<Kind, { title: string; row: string; under: string; label: string; placeholder: string; goes: readonly string[]; stays: string }> = {
  contact: {
    title: "Erase a contact",
    row: "A contact",
    under: "Every call a person was on, and every memory kept of them.",
    label: "Their number, or the id their calls carried",
    placeholder: "+14155550142",
    goes: [`Every call they were on in ${WORLD}`, "Each call's log, facts and recording", "Every memory the agents kept of them"],
    stays: "The dial ledger keeps the numbers and the time, for a carrier's traceback. A row of the trail says the erasure happened.",
  },
  call: {
    title: "Erase one call",
    row: "One call",
    under: "An ended call, by its id.",
    label: "The call's id",
    placeholder: "call_…",
    goes: ["The call's log, turn by turn", "The facts it collected", "The memories it taught", "Its recording"],
    stays: "The dial ledger keeps the numbers and the time, for a carrier's traceback. A row of the trail says the erasure happened.",
  },
};

const WHAT_ICONS: Record<string, IconName> = { call: "calls", contact: "numbers", agent: "agents", org: "building" };

function tookOf(row: Erasure): string {
  return `${many(row.calls, "call")}, ${many(row.entries, "entry", "entries")}, ${many(row.memories, "memory", "memories")}, ${many(row.recordings, "recording")}`;
}

function ErasePanel({ kind, onErased, onClose }: { kind: Kind; onErased: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const { busy, refused, move } = useMove();
  const [subject, setSubject] = useState("");
  const [done, setDone] = useState<Erasure | null>(null);
  const said = ERASES[kind];
  const wanted = subject.trim();

  const erase = (): void =>
    void move(() => (kind === "contact" ? eraseContact(credentials, wanted) : eraseCall(credentials, wanted))).then(
      (took) => {
        setDone(took);
        setSubject("");
        onErased();
      },
      () => undefined,
    );

  return (
    <SidePanel
      title={said.title}
      icon="close"
      about="It cannot be undone, and nothing of it can be brought back."
      onClose={onClose}
      footer={
        <>
          {refused !== null && (
            <p className="cfg-refused" role="alert">
              {refused}
            </p>
          )}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Close
            </button>
            {wanted === "" || busy ? (
              <button type="button" className="app-button app-button-danger" disabled>
                {busy ? "Erasing…" : "Erase"}
              </button>
            ) : (
              <ConfirmButton key={wanted} label={`Erase ${wanted}`} asks={`Erase ${wanted} for good?`} danger onConfirm={erase} />
            )}
          </div>
        </>
      }
    >
      <Field label={said.label}>
        <input className="cfg-input prv-mono" aria-label={said.label} placeholder={said.placeholder} autoFocus value={subject} onChange={(event) => (setSubject(event.target.value), setDone(null))} />
      </Field>
      <Field label="What goes">
        <ul className="prv-goes">
          {said.goes.map((one) => (
            <li key={one}>{one}</li>
          ))}
        </ul>
      </Field>
      <p className="prv-stays">{said.stays}</p>
      {done !== null && (
        <div className="tst-last tst-last-held">
          <span className="tst-last-top">
            <b>Erased {done.subject}</b>
          </span>
          <span className="tst-last-why">{tookOf(done)} went.</span>
        </div>
      )}
    </SidePanel>
  );
}

function ErasurePanel({ row, names, onClose }: { row: Erasure; names: Names; onClose: () => void }): ReactNode {
  return (
    <SidePanel title={row.subject} icon={WHAT_ICONS[row.what] ?? "close"} about={`Erased ${ago(row.at)}. This row is kept after the data, and after the organization.`} onClose={onClose}>
      <dl className="tst-facts">
        <div>
          <dt>What</dt>
          <dd>{row.what}</dd>
        </div>
        <div>
          <dt>Subject</dt>
          <dd>
            <Copy text={row.subject} bare />
          </dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>{dayAndTime(row.at)}</dd>
        </div>
        <div>
          <dt>Who asked</dt>
          <dd>{whoOf(names, row.asked_by)}</dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>{row.env ?? "Both"}</dd>
        </div>
      </dl>
      <Field label="What went">
        <dl className="tst-facts">
          <div>
            <dt>Calls</dt>
            <dd>{row.calls.toLocaleString("en-US")}</dd>
          </div>
          <div>
            <dt>Log entries</dt>
            <dd>{row.entries.toLocaleString("en-US")}</dd>
          </div>
          <div>
            <dt>Memories</dt>
            <dd>{row.memories.toLocaleString("en-US")}</dd>
          </div>
          <div>
            <dt>Recordings</dt>
            <dd>{row.recordings.toLocaleString("en-US")}</dd>
          </div>
        </dl>
      </Field>
    </SidePanel>
  );
}

function ExportSection(): ReactNode {
  const credentials = useCredentials();
  const { busy, refused, move } = useMove();
  const [saved, setSaved] = useState<string | null>(null);

  const download = (): void =>
    void move(() => exportWorld(credentials)).then(
      ({ file, name }) => {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(file);
        link.download = name;
        link.click();
        // Revoked once the browser has taken the download: revoked at once, some abort it.
        window.setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
        setSaved(name);
      },
      () => undefined,
    );

  return (
    <section className="tst-list tst-tone-blue" aria-label="Export">
      <Head icon="file" title="Export" about={`Everything ${WORLD} keeps, as one file.`} />
      <div className="tst-row">
        <span className="tst-row-main prv-row-plain">
          <span className="tst-mark" aria-hidden="true">
            <Icon name="file" size={14} />
          </span>
          <span className="tst-row-words">
            <span className="tst-row-name">The whole of {WORLD}</span>
            <span className="tst-row-under">Calls with their logs, memories, every agent's settings, and knowledge, as JSON Lines. Recordings stay on each call.</span>
          </span>
        </span>
        <span className="prv-row-end">
          {saved !== null && !busy && <span className="prv-good">Saved {saved}</span>}
          <button type="button" className="app-button" disabled={busy} onClick={download}>
            {busy ? "Exporting…" : "Download"}
          </button>
        </span>
      </div>
      {refused !== null && (
        <p className="cfg-refused tst-none" role="alert">
          {refused}
        </p>
      )}
    </section>
  );
}

export function EraseTab({ names }: { names: Names }): ReactNode {
  const credentials = useCredentials();
  const [trail, setTrail] = useState<Erasure[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [all, setAll] = useState(false);
  const [round, setRound] = useState(0);
  const close = useCallback(() => setOpen(null), []);
  const reread = useCallback(() => setRound((was) => was + 1), []);

  useEffect(() => {
    let gone = false;
    readTrail(credentials).then((read) => !gone && (setTrail(read), setRefused(null)), (failed: unknown) => !gone && (setTrail([]), setRefused(saidBy(failed))));
    return () => {
      gone = true;
    };
  }, [credentials, round]);

  const shown = all ? (trail ?? []) : (trail ?? []).slice(0, A_FEW);
  const openErasure = open?.panel === "erasure" ? (trail ?? []).find((one) => one.id === open.id) : undefined;

  return (
    <>
      <ExportSection />

      <section className="tst-list prv-tone-red" aria-label="Erase">
        <Head icon="close" title="Erase" about="A person's data gone for good. It cannot be undone." />
        {(Object.keys(ERASES) as Kind[]).map((kind) => (
          <div key={kind} className={open?.panel === kind ? "tst-row tst-row-on" : "tst-row"}>
            <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: kind })}>
              <span className="tst-mark" aria-hidden="true">
                <Icon name={WHAT_ICONS[kind] ?? "close"} size={14} />
              </span>
              <span className="tst-row-words">
                <span className="tst-row-name">{ERASES[kind].row}</span>
                <span className="tst-row-under dash-clip">{ERASES[kind].under}</span>
              </span>
              <span className="tst-row-when">Erase…</span>
            </button>
          </div>
        ))}
      </section>

      <section className="tst-list tst-tone-gold" aria-label="Erasure trail">
        <Head icon="clock" title="Erasure trail" about="Every erasure, from here, the CLI, the API or the retention run. Both environments.">
          {trail !== null && trail.length > 0 && <span className="tst-head-stands">{trail.length}</span>}
        </Head>
        {refused !== null && (
          <p className="cfg-refused tst-none" role="alert">
            {refused}
          </p>
        )}
        {trail === null && <p className="dash-quiet tst-none">Reading…</p>}
        {shown.map((row) => (
          <div key={row.id} className={openErasure?.id === row.id ? "tst-row tst-row-on" : "tst-row"}>
            <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: "erasure", id: row.id })}>
              <span className="tst-mark" aria-hidden="true">
                <Icon name={WHAT_ICONS[row.what] ?? "close"} size={14} />
              </span>
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <span className="dash-clip prv-mono">{row.subject}</span>
                  <span className="tst-tag">{row.what}</span>
                  {row.env != null && <span className="tst-tag">{row.env}</span>}
                </span>
                <span className="tst-row-under dash-clip">{tookOf(row)}</span>
              </span>
              <span className="prv-who dash-clip">{whoOf(names, row.asked_by)}</span>
              <span className="tst-row-when prv-row-when">{ago(row.at)}</span>
            </button>
          </div>
        ))}
        {trail !== null && refused === null && trail.length === 0 && <p className="dash-quiet tst-none">Nothing was erased yet.</p>}
        {(trail ?? []).length > A_FEW && !all && (
          <button type="button" className="tst-shelf" onClick={() => setAll(true)}>
            Show all {(trail ?? []).length}
          </button>
        )}
      </section>

      {(open?.panel === "contact" || open?.panel === "call") && <ErasePanel key={open.panel} kind={open.panel} onErased={reread} onClose={close} />}
      {openErasure !== undefined && <ErasurePanel key={openErasure.id} row={openErasure} names={names} onClose={close} />}
    </>
  );
}
