/** The access log tab: who read what of which call or number, and when; found by subject, narrowed by kind. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../lib/format";
import { Icon, type IconName } from "../shell/icons";
import { Select } from "../ui/select";
import { readReads, type DataRead } from "./door";
import { dayAndTime, Head, whoOf, type Names } from "./parts";

// How many reads are drawn at once, and how many the gateway gives at most.
const A_PAGE = 30;
const THE_DOORS_MOST = 200;
const EVERY_KIND = "";

const KINDS: Record<string, { name: string; icon: IconName }> = {
  log: { name: "Call log", icon: "calls" },
  recording: { name: "Recording", icon: "speaker" },
  traceback: { name: "Carrier traceback", icon: "route" },
  listen: { name: "Listened in", icon: "ear" },
  supervise: { name: "Took over", icon: "team" },
  export: { name: "Export", icon: "file" },
  memory: { name: "Memory", icon: "brain" },
};

const kindOf = (what: string): { name: string; icon: IconName } => KINDS[what] ?? { name: what, icon: "file" };

export function ReadsTab({ names }: { names: Names }): ReactNode {
  const credentials = useCredentials();
  const [rows, setRows] = useState<DataRead[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  // The subject the rows on screen were asked for; null is every subject.
  const [subject, setSubject] = useState<string | null>(null);
  const [kind, setKind] = useState(EVERY_KIND);
  const [shown, setShown] = useState(A_PAGE);

  useEffect(() => {
    let gone = false;
    setRows(null);
    readReads(credentials, subject).then((read) => !gone && (setRows(read), setRefused(null), setShown(A_PAGE)), (failed: unknown) => !gone && (setRows([]), setRefused(saidBy(failed))));
    return () => {
      gone = true;
    };
  }, [credentials, subject]);

  const find = (event: FormEvent): void => {
    event.preventDefault();
    setSubject(typed.trim() === "" ? null : typed.trim());
  };
  const clear = (): void => {
    setTyped("");
    setSubject(null);
  };

  const all = rows ?? [];
  const present = Object.keys(KINDS).filter((one) => all.some((row) => row.what === one));
  const matching = all.filter((row) => kind === EVERY_KIND || row.what === kind);

  return (
    <section className="tst-list prv-tone-accent" aria-label="Access log">
      <Head icon="search" title="Access log" about="Every read of a call, a recording or a memory. Written once an hour per reader and kind.">
        {rows !== null && all.length > 0 && <span className="tst-head-stands">{all.length >= THE_DOORS_MOST ? `Latest ${THE_DOORS_MOST}` : matching.length}</span>}
      </Head>
      <form className="prv-ask" onSubmit={find}>
        <input className="cfg-input prv-mono" aria-label="A call id or a number" placeholder="A call id or a number" value={typed} onChange={(event) => setTyped(event.target.value)} />
        <button type="submit" className="app-button">
          Find
        </button>
        {subject !== null && (
          <button type="button" className="app-button" onClick={clear}>
            Show all
          </button>
        )}
        {present.length > 1 && (
          <Select
            label="Kind of read"
            searchable={false}
            items={[{ value: EVERY_KIND, label: "Every kind" }, ...present.map((one) => ({ value: one, label: kindOf(one).name, tags: <span className="tst-tag">{all.filter((row) => row.what === one).length}</span> }))]}
            value={kind}
            onChange={(next) => (setKind(next), setShown(A_PAGE))}
          />
        )}
      </form>
      {refused !== null && (
        <p className="cfg-refused tst-none" role="alert">
          {refused}
        </p>
      )}
      {rows === null && <p className="dash-quiet tst-none">Reading…</p>}
      {matching.slice(0, shown).map((row, at) => {
        const said = kindOf(row.what);
        return (
          <div key={`${row.at}-${row.subject}-${row.what}-${at}`} className="tst-row">
            <span className="tst-row-main prv-row-plain">
              <span className="tst-mark" aria-hidden="true">
                <Icon name={said.icon} size={14} />
              </span>
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <span className="dash-clip">{said.name}</span>
                  {row.env != null && <span className="tst-tag">{row.env}</span>}
                </span>
                <span className="tst-row-under dash-clip prv-mono">{row.subject}</span>
              </span>
              <span className="prv-who dash-clip">{whoOf(names, row.reader)}</span>
              <span className="tst-row-when prv-row-when" title={dayAndTime(row.at)}>
                {ago(row.at)}
              </span>
            </span>
          </div>
        );
      })}
      {rows !== null && refused === null && matching.length === 0 && <p className="dash-quiet tst-none">{subject === null && kind === EVERY_KIND ? "Nobody has read a call yet." : "No reads match."}</p>}
      {matching.length > shown && (
        <button type="button" className="tst-shelf" onClick={() => setShown(shown + A_PAGE)}>
          Show {Math.min(A_PAGE, matching.length - shown)} more
        </button>
      )}
      {rows !== null && subject === null && all.length >= THE_DOORS_MOST && <p className="dash-quiet tst-none">These are the latest {THE_DOORS_MOST}. Find an older read by its call or number.</p>}
    </section>
  );
}
