/** Routes: every number the box answers at, of every org and world — how it came, and what a call to it does now. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { Card, CardFoot, CardHead, Empty, Input, Page, PageHead, Pill, Refused, TableHead, TableRow } from "../../ui";
import { cameIn, matching, whenItRings } from "./box-numbers";
import { readBoxNumbers } from "./door-floor";
import { useDoor } from "./use-door";
import "./box.css";

const COLUMNS = "minmax(0,1.1fr) minmax(0,1fr) 100px minmax(0,1fr) 84px minmax(0,1fr) minmax(0,1.2fr)";

/**
 * The screen. It changes nothing: a number is added, moved or let go from its org's Numbers screen,
 * which writes the carrier, the SFU and the route together. A row opens the number's Traceback.
 */
export function BoxRoutes(): ReactNode {
  const credentials = useCredentials();
  const numbers = useDoor(useCallback(() => readBoxNumbers(credentials), [credentials]));
  const [words, setWords] = useState("");
  const shown = matching(numbers.value ?? [], words);

  return (
    <Page width={1060} tight>
      <PageHead title="Routes" lede="Every number this box answers at, of every org and world, and what a call to it does now." />

      <Refused>{numbers.refused}</Refused>

      {numbers.value !== undefined && (
        <Card>
          <CardHead
            title="On this box"
            meta={`${numbers.value.length} ${numbers.value.length === 1 ? "number" : "numbers"}`}
            action={
              <span className="box-head-moves">
                <Input value={words} placeholder="Search a number, org or agent" aria-label="Search numbers" onChange={(event) => setWords(event.target.value)} />
              </span>
            }
          />
          {numbers.value.length === 0 ? (
            <Empty>No number on this box yet: an org adds one from its Numbers screen.</Empty>
          ) : shown.length === 0 ? (
            <Empty>No number, org or agent matches “{words.trim()}”.</Empty>
          ) : (
            <>
              <TableHead columns={COLUMNS} labels={["Number", "Org", "World", "Agent", "Channel", "Came in", "If it rings now"]} />
              {shown.map((row) => {
                const rings = whenItRings(row);
                return (
                  <TableRow key={`${row.org}-${row.channel}-${row.number}`} columns={COLUMNS} to={`/box/traceback?number=${encodeURIComponent(row.number)}`}>
                    <span className="ui-cell-strong">{prettyNumber(row.number)}</span>
                    <span className="ui-cell-ink ui-clip">{row.org}</span>
                    <span className="ui-cell-ink">{row.env}</span>
                    <span className="ui-cell-ink ui-clip">{row.agent}</span>
                    <span className="ui-cell-ink">{row.channel}</span>
                    <span className="ui-cell-ink ui-clip">{cameIn(row)}</span>
                    <span className="box-line">
                      <Pill tone={rings.tone}>{rings.text}</Pill>
                    </span>
                  </TableRow>
                );
              })}
            </>
          )}
          <CardFoot>To add, move or let go a number, open its org&apos;s Numbers screen: it writes the carrier, the SFU and the route together.</CardFoot>
        </Card>
      )}
    </Page>
  );
}
