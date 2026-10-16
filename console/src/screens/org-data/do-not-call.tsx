/** Consent and the do-not-call list: a number looked up, a consent given, a number put on the list, the list and an import. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { useWorld } from "../../lib/world";
import { Button, Card, CardHead, Empty, Input, Pill, Select, SelectItem, TableHead, TextAction, TextArea, type Tone } from "../../ui";
import { giveConsent, importDoNotCall, optOut, readConsent, readDoNotCall, type ConsentHistory, type DoNotCall } from "./door";

const LIST_COLUMNS = "minmax(0,1fr) 150px minmax(0,1.4fr) minmax(0,1fr)";

const STANDING: Record<ConsentHistory["standing"], [Tone, string]> = {
  consented: ["green", "consented"],
  opted_out: ["red", "do not call"],
  unknown: ["gray", "nothing on file"],
};

/**
 * A call to a US or Canadian number in production needs a consent on file, and a number on the
 * list is never dialled: this is where both are read and written, besides the API and the agent's
 * own opt-out.
 */
export function DoNotCallCard({ onRefused }: { onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const [page, setPage] = useState<DoNotCall | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const reread = async (after: string | null): Promise<void> => {
    try {
      setPage(await readDoNotCall(credentials, after));
      setCursor(after);
    } catch (failed) {
      onRefused(saidBy(failed));
    }
  };

  useEffect(() => {
    let gone = false;
    readDoNotCall(credentials, null).then(
      (first) => {
        if (!gone) setPage(first);
      },
      (failed: unknown) => {
        if (!gone) onRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, onRefused]);

  return (
    <>
      <Card>
        <CardHead title="Check a number" meta="has it agreed to be called, or asked not to be?" />
        <div className="data-body">
          <p className="data-sentence">
            {world === "production"
              ? "A call to a US or Canadian number needs the person's consent, recorded here or sent when the call is placed. A number on the do-not-call list is never called, even with consent attached: only a consent recorded here, or through the API, lifts it."
              : "This is the sandbox's own list, for trying things out. The sandbox places calls without checking consent or the list; production keeps a separate list."}
          </p>
          <LookUp onChanged={() => reread(cursor)} onRefused={onRefused} />
        </div>
      </Card>

      <Card>
        <CardHead
          title="Do-not-call list"
          meta="numbers that are never called. An agent adds a caller by itself when they ask to stop."
          action={<TextAction onClick={() => setImporting(!importing)}>{importing ? "Close" : "Import a list"}</TextAction>}
        />
        {importing && (
          <div className="data-body">
            <Import onImported={() => reread(null)} onRefused={onRefused} />
          </div>
        )}
        <div className="data-list">
          {page !== null && page.numbers.length === 0 ? (
            <Empty>No number is on the list.</Empty>
          ) : (
            <>
              <TableHead columns={LIST_COLUMNS} labels={["Number", "Since", "From", "Added by"]} />
              {(page?.numbers ?? []).map((opted) => (
                <div key={opted.number} className="ui-table-row data-row" style={{ gridTemplateColumns: LIST_COLUMNS }}>
                  <span className="ui-cell-ink ui-fixed">{opted.number}</span>
                  <span className="ui-cell-faint">{dayAndTime(opted.since)}</span>
                  <span className="ui-cell-faint ui-clip">{opted.source}</span>
                  <span className="ui-cell-faint ui-clip">{opted.given_by}</span>
                </div>
              ))}
              {page?.next != null && (
                <div className="data-more">
                  <Button size="sm" onClick={() => void reread(page.next)}>
                    Older
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </Card>
    </>
  );
}

/** One number: what stands for it, its history, a consent given, the number put on the list. */
function LookUp({ onChanged, onRefused }: { onChanged: () => Promise<void>; onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const [number, setNumber] = useState("");
  const [shown, setShown] = useState<ConsentHistory | null>(null);
  const [kind, setKind] = useState<"express" | "written">("express");
  const [source, setSource] = useState("");
  const [words, setWords] = useState("");
  const [busy, setBusy] = useState(false);

  const does = async (what: () => Promise<ConsentHistory>): Promise<void> => {
    setBusy(true);
    onRefused(null);
    try {
      setShown(await what());
      await onChanged();
    } catch (failed) {
      onRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const look = (event: FormEvent): void => {
    event.preventDefault();
    if (number.trim() !== "") void does(() => readConsent(credentials, number.trim()));
  };

  const give = (event: FormEvent): void => {
    event.preventDefault();
    if (shown === null || source.trim() === "") {
      onRefused("A consent says where it came from: a form, a call, a signed paper.");
      return;
    }
    void does(() => giveConsent(credentials, { number: shown.number, kind, source: source.trim(), text: words.trim() === "" ? null : words.trim() }));
  };

  const [tone, said]: [Tone, string] = shown === null ? ["gray", ""] : STANDING[shown.standing];

  return (
    <div className="data-lookup">
      <form className="data-form" onSubmit={look}>
        <Input value={number} aria-label="A number to look up" placeholder="Number, e.g. +14155550142" onChange={(event) => setNumber(event.target.value)} />
        <Button type="submit" size="form" disabled={busy || number.trim() === ""}>
          Check
        </Button>
      </form>
      {shown !== null && (
        <div className="data-consent">
          <div className="data-consent-head">
            <span className="ui-fixed">{shown.number}</span>
            <Pill tone={tone}>{said}</Pill>
            {shown.standing !== "opted_out" && (
              <Button size="xs" kind="danger" disabled={busy} onClick={() => void does(() => optOut(credentials, shown.number))}>
                Add to the do-not-call list
              </Button>
            )}
          </div>
          {shown.rows.map((row, index) => (
            <div key={`${row.given_at}-${index}`} className="data-consent-row">
              <span className="ui-cell-faint">{dayAndTime(row.given_at)}</span>
              <span>{row.kind === "opt_out" ? "opt-out" : `${row.kind} consent`}</span>
              <span className="ui-cell-faint ui-clip">
                {row.source} · {row.given_by}
                {row.call === null ? "" : ` · ${row.call}`}
              </span>
            </div>
          ))}
          <form className="data-form data-give" onSubmit={give}>
            <Select className="data-kind" aria-label="Kind of consent" value={kind} onValueChange={(value) => setKind(value === "written" ? "written" : "express")}>
              <SelectItem value="express">express consent</SelectItem>
              <SelectItem value="written">written consent</SelectItem>
            </Select>
            <Input value={source} aria-label="Where the consent came from" placeholder="Where it came from, e.g. the booking form" onChange={(event) => setSource(event.target.value)} />
            <Input value={words} aria-label="The words they agreed to" placeholder="What they agreed to (optional)" onChange={(event) => setWords(event.target.value)} />
            <Button type="submit" kind="primary" size="form" disabled={busy}>
              Record consent
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}

/** Numbers pasted one a line, the org's own list or its Registry scrub, onto the list at once. */
function Import({ onImported, onRefused }: { onImported: () => Promise<void>; onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const [lines, setLines] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const numbers = lines.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== "");
    if (numbers.length === 0 || source.trim() === "") {
      onRefused("Paste the numbers, one per line, and say where the list came from.");
      return;
    }
    setBusy(true);
    setDone(null);
    onRefused(null);
    try {
      const imported = await importDoNotCall(credentials, numbers, source.trim());
      setDone(`${imported.added} added${imported.refused.length === 0 ? "" : ` · not valid numbers: ${imported.refused.join(", ")}`}`);
      setLines("");
      await onImported();
    } catch (failed) {
      onRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="data-import" onSubmit={(event) => void submit(event)}>
      <TextArea rows={3} aria-label="Numbers to add, one per line" value={lines} placeholder={"One number per line:\n+14155550142\n+14155550143"} onChange={(event) => setLines(event.target.value)} />
      <div className="data-form">
        <Input value={source} aria-label="Where the list came from" placeholder="Where this list came from, e.g. National registry, Sept 2026" onChange={(event) => setSource(event.target.value)} />
        <Button type="submit" size="form" disabled={busy}>
          {busy ? "Importing…" : "Add these numbers"}
        </Button>
        {done !== null && <span className="data-done">{done}</span>}
      </div>
    </form>
  );
}
