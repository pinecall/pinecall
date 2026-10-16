/** Taking the world out and erasing a contact, and the trail every erasure leaves. */

import { useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { nameOf, useNames } from "../../lib/names";
import { useWorld } from "../../lib/world";
import { Button, Card, CardHead, Empty, Input, Pill, TableHead } from "../../ui";
import { eraseContact, exportWorld, type Erasure } from "./door";

const COLUMNS = "150px 90px minmax(0,1.2fr) minmax(0,1.6fr) minmax(0,1fr) 90px";

/** The whole world, downloaded as JSON Lines. */
export function TakeItOut({ onRefused }: { onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const [busy, setBusy] = useState(false);

  const download = async (): Promise<void> => {
    setBusy(true);
    onRefused(null);
    try {
      const { file, name } = await exportWorld(credentials);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(file);
      link.download = name;
      link.click();
      // Revoked once the browser has taken the download: revoked at once, some abort it.
      setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
    } catch (failed) {
      onRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card pad>
      <CardHead title="Export" meta={`${world}, whole`} />
      <p className="data-sentence">
        Every call with its whole log, every memory, every version of every agent's settings and words, and every knowledge document, as one file of JSON Lines. Recordings stay on each call's page.
      </p>
      <Button size="form" disabled={busy} onClick={() => void download()}>
        {busy ? "Exporting…" : "Download the export"}
      </Button>
    </Card>
  );
}

/** A person's "delete my data": every call they were on in this world, and every fact kept of them. */
export function EraseAContact({ onErased, onRefused }: { onErased: () => Promise<void>; onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const [who, setWho] = useState("");
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Erasure | null>(null);

  const erase = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (who.trim() === "") return;
    if (!sure) {
      setSure(true);
      return;
    }
    setBusy(true);
    onRefused(null);
    try {
      setDone(await eraseContact(credentials, who.trim()));
      setWho("");
      setSure(false);
    } catch (failed) {
      onRefused(saidBy(failed));
      setBusy(false);
      return;
    }
    // The erasure is done whatever the trail's re-read says: a refusal there is its own.
    await onErased();
    setBusy(false);
  };

  return (
    <Card pad>
      <CardHead title="Erase a contact" meta="cannot be undone" />
      <p className="data-sentence">The number or the id a call carried. Every call they were on in this world goes, with every fact the agents kept of them. The dial ledger keeps the numbers and the time, for a carrier's traceback.</p>
      <form className="data-form" onSubmit={(event) => void erase(event)}>
        <Input value={who} aria-label="The number or the id a call carried" placeholder="+14155550142" onChange={(event) => { setWho(event.target.value); setSure(false); }} />
        <Button type="submit" kind={sure ? "danger" : "primary"} size="form" disabled={busy || who.trim() === ""}>
          {busy ? "Erasing…" : sure ? `Erase ${who.trim()} for good` : "Erase"}
        </Button>
      </form>
      {done !== null && <p className="data-done">{tookLine(done)}</p>}
    </Card>
  );
}

/** Every erasure of the org, newest first. */
export function Trail({ rows }: { rows: Erasure[] | null }): ReactNode {
  const names = useNames();
  return (
    <Card>
      <CardHead title="Erasures" meta="both worlds · newest first · kept after the org" />
      {rows !== null && rows.length === 0 ? (
        <Empty>Nothing erased yet.</Empty>
      ) : (
        <>
          <TableHead columns={COLUMNS} labels={["When", "What", "Which", "What went", "Who asked", "World"]} />
          {(rows ?? []).map((row) => (
            <div key={row.id} className="ui-table-row data-row" style={{ gridTemplateColumns: COLUMNS }}>
              <span className="ui-cell-faint">{dayAndTime(row.at)}</span>
              <span>
                <Pill tone={row.what === "org" ? "red" : "gray"}>{row.what}</Pill>
              </span>
              <span className="ui-cell-ink ui-clip" title={row.subject}>
                {row.subject}
              </span>
              <span className="ui-cell-faint ui-clip">{tookLine(row)}</span>
              <span className="ui-cell-faint ui-clip" title={row.asked_by}>
                {nameOf(names, row.asked_by)}
              </span>
              <span className="ui-cell-faint">{row.env ?? "—"}</span>
            </div>
          ))}
        </>
      )}
    </Card>
  );
}

function tookLine(row: Erasure): string {
  return `${row.calls} call${row.calls === 1 ? "" : "s"}, ${row.entries} entries, ${row.memories} memories, ${row.recordings} recording${row.recordings === 1 ? "" : "s"}`;
}
