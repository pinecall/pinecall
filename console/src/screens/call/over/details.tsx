/** Collapsible details under a finished call: consent, prompt blocks, full log. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation } from "react-router";

import { Card, CardHead, KV } from "../../../ui";
import { Consents, consents } from "./consent";
import { Timeline } from "./timeline";
import { transcript } from "./transcript";

// A `#seq-N` fragment opens the details; timeline.tsx scrolls to the row once rendered.
const A_SEQ = /^#seq-\d+$/;

/** Rendered lazily on open. `beside` sits on the bar's right. */
export function Details({ state, entries, beside }: { state: State; entries: Entry[]; beside?: ReactNode }): ReactNode {
  const { hash } = useLocation();
  const [open, setOpen] = useState(() => A_SEQ.test(hash));
  const read = useMemo(() => ({ consented: consents(entries), lines: transcript(entries) }), [entries]);

  useEffect(() => {
    if (A_SEQ.test(hash)) setOpen(true);
  }, [hash]);

  return (
    <>
      <div className="over-bar">
        <button type="button" className="over-details" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="over-details-caret">{open ? "▾" : "▸"}</span>
          <span className="over-details-name">Details</span>
          <span className="over-details-what">consent, prompt blocks, the full log</span>
        </button>
        {beside}
      </div>
      {open && read.consented.length > 0 && (
        <Card>
          <CardHead title="Consent proof" meta="each grant joined to the tool call it authorised" />
          <Consents rows={read.consented} />
        </Card>
      )}
      {open && Object.keys(state.prompt).length > 0 && (
        <Card>
          <CardHead title="The prompt, block by block" meta="by name, hash and length — the text never enters the log" />
          <div className="over-prompt">
            {Object.entries(state.prompt).map(([name, block]) => (
              <KV key={name} label={name}>
                <span className="ui-fixed over-hash">{block.hash}</span> · {block.chars} chars · seq {block.seq}
              </KV>
            ))}
          </div>
          <div className="over-note">
            <span className="ui-fixed">pinecall prompt --state</span> prints the text offline.
          </div>
        </Card>
      )}
      {open && <Timeline lines={read.lines} turns={state.turns} />}
    </>
  );
}
