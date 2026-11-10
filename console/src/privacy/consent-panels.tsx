/** The panels of the consent tab: one number with what stands for it and its history, and many numbers put on the do-not-call list at once. */

import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { useMove } from "../numbers/parts";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { giveConsent, importDoNotCall, optOut, readConsent, type ConsentHistory, type ConsentKind, type Imported } from "./door";
import { dayAndTime, many, whoOf, type Names } from "./parts";

const STANDING: Record<ConsentHistory["standing"], { mood: "held" | "broke" | "none"; title: string; about: string }> = {
  consented: { mood: "held", title: "Consented", about: "It may be called." },
  opted_out: { mood: "broke", title: "Do not call", about: "It is never called. Only a new consent lifts it." },
  unknown: { mood: "none", title: "Nothing on file", about: "No consent, and not on the list." },
};

const KINDS: readonly { value: ConsentKind; name: string }[] = [
  { value: "express", name: "Express" },
  { value: "written", name: "Written" },
];

const kindOf = (kind: string): string => (kind === "opt_out" ? "Opted out" : kind === "written" ? "Written consent" : kind === "express" ? "Express consent" : kind);

/** `onChanged` is told after a write, so the list behind the panel reads again. */
export function NumberPanel({ number, names, onChanged, onClose }: { number: string; names: Names; onChanged: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const form = useId();
  const { busy, refused, move } = useMove();
  const [shown, setShown] = useState<ConsentHistory | null>(null);
  const [unread, setUnread] = useState<string | null>(null);
  const [kind, setKind] = useState<ConsentKind>("express");
  const [source, setSource] = useState("");
  const [words, setWords] = useState("");

  useEffect(() => {
    let gone = false;
    readConsent(credentials, number).then((read) => !gone && setShown(read), (failed: unknown) => !gone && setUnread(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials, number]);

  // A refusal is said by `move`; nothing else is left to do with it here.
  const write = (work: () => Promise<ConsentHistory>): void =>
    void move(work).then(
      (now) => {
        setShown(now);
        setSource("");
        setWords("");
        onChanged();
      },
      () => undefined,
    );

  const give = (event: FormEvent): void => {
    event.preventDefault();
    if (shown === null) return;
    write(() => giveConsent(credentials, { number: shown.number, kind, source: source.trim(), text: words.trim() === "" ? null : words.trim() }));
  };

  const standing = shown === null ? null : STANDING[shown.standing];
  return (
    <SidePanel
      title={shown?.number ?? number}
      icon="numbers"
      onClose={onClose}
      footer={
        shown === null ? undefined : (
          <>
            {refused !== null && (
              <p className="cfg-refused" role="alert">
                {refused}
              </p>
            )}
            <div className={shown.standing === "opted_out" ? "cfg-dialog-foot" : "cfg-dialog-foot prv-foot-wide"}>
              {shown.standing !== "opted_out" && <ConfirmButton label="Put on the do-not-call list" asks="Never call it again?" danger onConfirm={() => write(() => optOut(credentials, shown.number))} />}
              <button type="submit" form={form} className="cfg-save" disabled={busy || source.trim() === ""}>
                {busy ? "Saving…" : "Record consent"}
              </button>
            </div>
          </>
        )
      }
    >
      {unread !== null && (
        <p className="cfg-refused" role="alert">
          {unread}
        </p>
      )}
      {shown === null && unread === null && <p className="dash-quiet">Reading…</p>}
      {shown !== null && standing !== null && (
        <>
          <div className={`tst-last tst-last-${standing.mood}`}>
            <span className="tst-last-top">
              <b>{standing.title}</b>
              <span className="dash-quiet">{standing.about}</span>
            </span>
          </div>
          <Field label="History">
            {shown.rows.length === 0 ? (
              <p className="dash-quiet">Nothing was ever recorded for it.</p>
            ) : (
              <div className="prv-history">
                {shown.rows.map((row, at) => (
                  <div key={`${row.given_at}-${at}`} className="prv-history-row">
                    <span className="prv-history-top">
                      <b>{kindOf(row.kind)}</b>
                      <span className="dash-quiet">{dayAndTime(row.given_at)}</span>
                    </span>
                    <span className="dash-quiet">
                      {row.source}, by {whoOf(names, row.given_by)}
                      {row.call == null ? "" : `, on call ${row.call}`}
                    </span>
                    {row.text != null && row.text !== "" && <span className="prv-history-words">“{row.text}”</span>}
                  </div>
                ))}
              </div>
            )}
          </Field>
          <form id={form} className="cfg-dialog-body" onSubmit={give}>
            <Field label="Record a consent">
              <div className="dash-switch prv-kinds" role="group" aria-label="Kind of consent">
                {KINDS.map((one) => (
                  <button key={one.value} type="button" aria-pressed={kind === one.value} className={kind === one.value ? "dash-switch-on" : ""} onClick={() => setKind(one.value)}>
                    {one.name}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Where it came from">
              <input className="cfg-input" aria-label="Where the consent came from" placeholder="The booking form" value={source} onChange={(event) => setSource(event.target.value)} />
            </Field>
            <Field label="What they agreed to">
              <textarea className="cfg-input cfg-area" rows={3} aria-label="The words they agreed to" placeholder="Optional. The exact words shown or said." value={words} onChange={(event) => setWords(event.target.value)} />
            </Field>
          </form>
        </>
      )}
    </SidePanel>
  );
}

export function ImportPanel({ onImported, onClose }: { onImported: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const form = useId();
  const { busy, refused, move } = useMove();
  const [lines, setLines] = useState("");
  const [source, setSource] = useState("");
  const [done, setDone] = useState<Imported | null>(null);
  const numbers = lines.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== "");

  const add = (event: FormEvent): void => {
    event.preventDefault();
    setDone(null);
    void move(() => importDoNotCall(credentials, numbers, source.trim())).then(
      (imported) => {
        setDone(imported);
        setLines("");
        onImported();
      },
      () => undefined,
    );
  };

  return (
    <SidePanel
      title="Import numbers"
      icon="plus"
      about="Numbers that must never be called: your own list, or a registry's."
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
            <button type="submit" form={form} className="cfg-save" disabled={busy || numbers.length === 0 || source.trim() === ""}>
              {busy ? "Adding…" : numbers.length === 0 ? "Add to the list" : `Add ${many(numbers.length, "number")}`}
            </button>
          </div>
        </>
      }
    >
      <form id={form} className="cfg-dialog-body" onSubmit={add}>
        <Field label="Numbers, one a line">
          <textarea className="cfg-input cfg-area prv-mono" rows={9} aria-label="Numbers to add, one a line" placeholder={"+14155550142\n+14155550143"} autoFocus value={lines} onChange={(event) => setLines(event.target.value)} />
        </Field>
        <Field label="Where the list came from">
          <input className="cfg-input" aria-label="Where the list came from" placeholder="National registry, November 2026" value={source} onChange={(event) => setSource(event.target.value)} />
        </Field>
      </form>
      {done !== null && (
        <div className={`tst-last ${done.refused.length === 0 ? "tst-last-held" : "tst-last-broke"}`}>
          <span className="tst-last-top">
            <b>{many(done.added, "number")} added</b>
            <span className="dash-quiet">{done.refused.length === 0 ? "Every line was a number." : `${many(done.refused.length, "line")} refused`}</span>
          </span>
          {done.refused.length > 0 && (
            <ul className="prv-refused-lines">
              {done.refused.map((line, at) => (
                <li key={`${line}-${at}`}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </SidePanel>
  );
}
