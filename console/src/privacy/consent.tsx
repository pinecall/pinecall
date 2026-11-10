/** The consent tab: a number looked up, and the do-not-call list, paged, with the way to import many. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../lib/format";
import { WORLD } from "../lib/world";
import { Icon } from "../shell/icons";
import { ImportPanel, NumberPanel } from "./consent-panels";
import { readDoNotCall, type DoNotCall } from "./door";
import { Head, whoOf, type Names } from "./parts";

type Open = { panel: "number"; number: string } | { panel: "import" };

export function ConsentTab({ names }: { names: Names }): ReactNode {
  const credentials = useCredentials();
  const [typed, setTyped] = useState("");
  const [open, setOpen] = useState<Open | null>(null);
  const [page, setPage] = useState<DoNotCall | null>(null);
  // The cursor of the page shown; null is the newest.
  const [after, setAfter] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  const [refused, setRefused] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const reread = useCallback(() => setRound((was) => was + 1), []);

  useEffect(() => {
    let gone = false;
    readDoNotCall(credentials, after).then((read) => !gone && (setPage(read), setRefused(null)), (failed: unknown) => !gone && (setPage({ numbers: [], next: null }), setRefused(saidBy(failed))));
    return () => {
      gone = true;
    };
  }, [credentials, after, round]);

  const look = (event: FormEvent): void => {
    event.preventDefault();
    if (typed.trim() !== "") setOpen({ panel: "number", number: typed.trim() });
  };
  const openNumber = open?.panel === "number" ? open.number : null;

  return (
    <>
      <section className="tst-list prv-tone-green" aria-label="Consent">
        <Head icon="check" title="Consent" about={WORLD === "production" ? "Whether a number agreed to be called, or asked not to be." : "The sandbox's own record. Sandbox calls check neither consent nor the list."} />
        <form className="prv-ask" onSubmit={look}>
          <input className="cfg-input prv-mono" type="tel" aria-label="A number to look up" placeholder="+14155550142" value={typed} onChange={(event) => setTyped(event.target.value)} />
          <button type="submit" className="cfg-save" disabled={typed.trim() === ""}>
            Look up
          </button>
        </form>
      </section>

      <section className="tst-list prv-tone-red" aria-label="Do-not-call list">
        <Head icon="pause" title="Do-not-call list" about="Numbers that are never called. An agent adds a caller who asks to stop.">
          <button type="button" className="cfg-save tst-action" onClick={() => setOpen({ panel: "import" })}>
            <Icon name="plus" size={12} />
            Import numbers
          </button>
        </Head>
        {refused !== null && (
          <p className="cfg-refused tst-none" role="alert">
            {refused}
          </p>
        )}
        {page === null && <p className="dash-quiet tst-none">Reading…</p>}
        {(page?.numbers ?? []).map((one) => (
          <div key={one.number} className={openNumber === one.number ? "tst-row tst-row-on" : "tst-row"}>
            <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: "number", number: one.number })}>
              <span className="tst-mark" aria-hidden="true">
                <Icon name="pause" size={14} />
              </span>
              <span className="tst-row-words">
                <span className="tst-row-name prv-mono">{one.number}</span>
                <span className="tst-row-under dash-clip">{one.source}</span>
              </span>
              <span className="prv-who dash-clip">{whoOf(names, one.given_by)}</span>
              <span className="tst-row-when prv-row-when">{ago(one.since)}</span>
            </button>
          </div>
        ))}
        {page !== null && refused === null && page.numbers.length === 0 && <p className="dash-quiet tst-none">{after === null ? "No number is on the list." : "No older numbers."}</p>}
        {(after !== null || page?.next != null) && (
          <div className="prv-pages">
            {after !== null && (
              <button type="button" className="tst-shelf" onClick={() => setAfter(null)}>
                Back to the newest
              </button>
            )}
            {page?.next != null && (
              <button type="button" className="tst-shelf" onClick={() => setAfter(page.next ?? null)}>
                Older
              </button>
            )}
          </div>
        )}
      </section>

      {openNumber !== null && <NumberPanel key={openNumber} number={openNumber} names={names} onChanged={reread} onClose={close} />}
      {open?.panel === "import" && <ImportPanel onImported={() => (setAfter(null), reread())} onClose={close} />}
    </>
  );
}
