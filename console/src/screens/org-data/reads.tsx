/** Who read what: a person reading a call's log or recording, the operator off the box or in a traceback. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { nameOf, useNames } from "../../lib/names";
import { Button, Card, CardHead, Chips, Empty, Input, Pill, TableHead } from "../../ui";
import { readReads, type Read } from "./door";

const COLUMNS = "150px 100px minmax(0,1.4fr) minmax(0,1fr) 100px";

const WHAT: Record<Read["what"], string> = {
  log: "Call log",
  recording: "Recording",
  traceback: "Carrier traceback",
  listen: "Listened in",
  supervise: "Took over",
  export: "Export",
  memory: "Memory",
};

const PAGE = 25;

/**
 * The org's access log, what a breach notification starts from. A read is written once an hour per
 * reader, call and kind; a server's key and a visitor's page write nothing.
 */
export function ReadsCard({ onRefused }: { onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const [rows, setRows] = useState<Read[] | null>(null);
  const names = useNames();
  const [subject, setSubject] = useState("");
  const [kind, setKind] = useState<Read["what"] | "all">("all");
  const [shown, setShown] = useState(PAGE);

  useEffect(() => {
    let gone = false;
    readReads(credentials, null).then(
      (read) => {
        if (!gone) setRows(read);
      },
      (failed: unknown) => {
        if (!gone) onRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, onRefused]);

  const look = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    try {
      setRows(await readReads(credentials, subject.trim() === "" ? null : subject.trim()));
      setShown(PAGE);
    } catch (failed) {
      onRefused(saidBy(failed));
    }
  };

  const kinds = (Object.keys(WHAT) as Read["what"][]).filter((one) => (rows ?? []).some((row) => row.what === one));
  const filtered = (rows ?? []).filter((row) => kind === "all" || row.what === kind);

  return (
    <Card pad>
      <CardHead title="Who read what" meta="newest first. Each reader, call and kind is written once an hour." />
      <p className="data-sentence">
        Every time someone opens a call's log or recording, listens in, takes over, exports data or reads what memory kept about a contact. Visitors on a web page are not recorded.
      </p>
      <form className="data-form" onSubmit={(event) => void look(event)}>
        <Input value={subject} aria-label="A call id or a number" placeholder="Find one call or number, e.g. call_abc or +14155550142" onChange={(event) => setSubject(event.target.value)} />
        <Button type="submit" size="form">
          Find
        </Button>
      </form>
      {kinds.length > 1 && (
        <div className="data-chips">
          <Chips
            options={[{ value: "all", label: `All ${(rows ?? []).length}` }, ...kinds.map((one) => ({ value: one, label: `${WHAT[one]} ${(rows ?? []).filter((row) => row.what === one).length}` }))]}
            value={kind}
            onChange={(next) => {
              setKind(next);
              setShown(PAGE);
            }}
          />
        </div>
      )}
      <div className="data-list">
        {rows !== null && filtered.length === 0 ? (
          <Empty>{subject.trim() === "" && kind === "all" ? "Nobody has read a call of this org yet." : "No reads match."}</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["When", "What", "Which", "Who", "World"]} />
            {filtered.slice(0, shown).map((row, index) => (
              <div key={`${row.at}-${index}`} className="ui-table-row data-row" style={{ gridTemplateColumns: COLUMNS }}>
                <span className="ui-cell-faint">{dayAndTime(row.at)}</span>
                <span>{WHAT[row.what]}</span>
                <span className="ui-cell-ink ui-clip ui-fixed">{row.subject}</span>
                <span className="ui-clip">{row.reader === "operator" ? <Pill tone="violet">Pinecall operator</Pill> : nameOf(names, row.reader)}</span>
                <span className="ui-cell-faint">{row.env ?? "—"}</span>
              </div>
            ))}
            {filtered.length > shown && (
              <div className="data-more">
                <Button size="sm" onClick={() => setShown(shown + PAGE)}>
                  Show {Math.min(PAGE, filtered.length - shown)} more
                </Button>
              </div>
            )}
          </>
        )}
      </div>
      {rows !== null && rows.length >= 200 && <p className="data-sentence data-note">Showing the latest 200. To find an older read, search for its call or number above.</p>}
    </Card>
  );
}
