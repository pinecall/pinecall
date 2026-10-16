/** Traceback: a number's phone calls in every org, kept or erased, and every dial to it — what a carrier asks for. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { dayAndTime } from "../../lib/format";
import { Button, Card, CardHead, Empty, Field, Input, Page, PageHead, Pill, Refused, TableHead, TableRow } from "../../ui";
import { readTraceback, type Traceback } from "./door-floor";
import { useMove } from "./use-door";
import "./box.css";

const CALLS = "130px 90px minmax(0,1fr) 70px minmax(0,1fr) minmax(0,1fr) 150px";
const DIALS = "130px minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr)";

const lasted = (from: number | null, until: number | null): string => (from === null || until === null ? "—" : `${Math.round(until - from)}s`);

/**
 * The screen. An erased call is still here as its detail record — numbers, times, how it ended —
 * for 24 months after it started; the dial ledger keeps every dial, placed or refused.
 */
export function BoxTraceback(): ReactNode {
  const credentials = useCredentials();
  const [search] = useSearchParams();
  // Opened from a row of Routes, `?number=` is looked up on arrival.
  const [number, setNumber] = useState(() => search.get("number") ?? "");
  const [day, setDay] = useState("");
  const [found, setFound] = useState<Traceback | null>(null);
  const acting = useMove();

  const lookUp = async (): Promise<void> => {
    const since = day === "" ? null : Date.parse(`${day}T00:00:00Z`) / 1000;
    await acting.move(async () => setFound(await readTraceback(credentials, number.trim(), since)));
  };

  const look = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    await lookUp();
  };

  // Once, with the number the page opened with; every later look-up is the form's.
  useEffect(() => {
    if (number.trim() !== "") void lookUp();
  }, []);

  return (
    <Page>
      <PageHead title="Traceback" lede="A number's phone calls in every org, and every dial to it: who placed a call, when, from which number." />
      <form className="ui-form box-inline" onSubmit={(event) => void look(event)}>
        <Field label="Number" minWidth={170}>
          <Input value={number} placeholder="+14155550142" onChange={(event) => setNumber(event.target.value)} required />
        </Field>
        <Field label="Since (24 months back unset)" minWidth={170}>
          <Input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
        </Field>
        <Button kind="primary" size="form" type="submit" disabled={acting.busy || number.trim() === ""}>
          {acting.busy ? "Looking…" : "Look up"}
        </Button>
      </form>

      <Refused>{acting.refused}</Refused>

      {found !== null && (
        <>
          <Card>
            <CardHead title={`Calls with ${prettyNumber(found.number)}`} meta={`since ${dayAndTime(found.since)} · ${found.calls.length}`} />
            {found.calls.length === 0 ? (
              <Empty>No phone call with this number.</Empty>
            ) : (
              <>
                <TableHead columns={CALLS} labels={["Started", "Way", "From → to", "Lasted", "Ended", "Org", "Call"]} />
                {found.calls.map((call) => (
                  <TableRow key={call.call} columns={CALLS}>
                    <span className="ui-cell-faint">{dayAndTime(call.started_at)}</span>
                    <span className="ui-cell-ink">{call.direction ?? "—"}</span>
                    <span className="ui-cell-ink ui-clip box-fixed">
                      {call.from_number ?? "—"} → {call.to_number ?? "—"}
                    </span>
                    <span className="ui-cell-faint">{lasted(call.started_at, call.ended_at)}</span>
                    <span className="ui-cell-faint ui-clip">{call.end_reason ?? "—"}</span>
                    <span className="ui-cell-ink ui-clip">
                      {call.org ?? "—"} · {call.env ?? "—"}
                    </span>
                    <span className="box-line">
                      <span className="ui-clip box-fixed">{call.call}</span>
                      {call.erased && <Pill tone="gray">record only</Pill>}
                    </span>
                  </TableRow>
                ))}
              </>
            )}
          </Card>
          <Card>
            <CardHead title="Dials" meta={String(found.dials.length)} />
            {found.dials.length === 0 ? (
              <Empty>No dial to this number.</Empty>
            ) : (
              <>
                <TableHead columns={DIALS} labels={["At", "Shown", "Org · agent", "Asked by", "What came of it"]} />
                {found.dials.map((dial, index) => (
                  <TableRow key={`${dial.at}-${index}`} columns={DIALS}>
                    <span className="ui-cell-faint">{dayAndTime(dial.at)}</span>
                    <span className="ui-cell-ink box-fixed">{dial.shown ?? "—"}</span>
                    <span className="ui-cell-ink ui-clip">
                      {dial.org} · {dial.env} · {dial.agent}
                    </span>
                    <span className="ui-cell-faint ui-clip">{dial.asked_by}</span>
                    <span className="ui-clip">{dial.refused === null ? <span className="box-fixed">{dial.call ?? "placed"}</span> : <Pill tone="red">{dial.refused}</Pill>}</span>
                  </TableRow>
                ))}
              </>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}
