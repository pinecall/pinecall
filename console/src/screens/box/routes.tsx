/** Routes: every number the box answers at, of every org and world — how it came, and what a call to it does now. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { Button, Card, CardFoot, CardHead, Empty, Input, Page, PageHead, Pill, Refused, TableHead, TableRow, TextAction } from "../../ui";
import { cameIn, matching, whenItRings } from "./box-numbers";
import { readTestLine, saveTestLine } from "./door-box";
import { readBoxNumbers } from "./door-floor";
import { useDoor, useMove } from "./use-door";
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

      <TestLine sandboxNumbers={(numbers.value ?? []).filter((row) => row.env === "sandbox" && row.channel === "phone").map((row) => row.number)} />

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

/**
 * The test line: one sandbox number of the box's own that a person calls, from the phone they said
 * was theirs, to reach their own sandbox agent. The number's own agent answers everybody else.
 */
function TestLine({ sandboxNumbers }: { sandboxNumbers: string[] }): ReactNode {
  const credentials = useCredentials();
  const line = useDoor(useCallback(() => readTestLine(credentials), [credentials]));
  const move = useMove();
  const [typed, setTyped] = useState("");

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (await move.move(() => saveTestLine(credentials, typed.trim()))) {
      setTyped("");
      await line.reread();
    }
  };
  const forget = async (): Promise<void> => {
    if (await move.move(() => saveTestLine(credentials, null))) await line.reread();
  };

  return (
    <Card>
      <CardHead title="The test line" meta={line.value === undefined ? undefined : line.value === null ? "none" : prettyNumber(line.value)} />
      <div className="box-line-body">
        <span className="ui-note">
          A person calls it from the phone they said was theirs (Phone testing) and their own sandbox agent answers. One of this box&apos;s numbers routed in the sandbox: its own
          agent answers anybody else, and should say so.
        </span>
        {line.value !== undefined && line.value !== null ? (
          <span className="box-line-row">
            <span className="ui-cell-strong">{prettyNumber(line.value)}</span>
            <TextAction onClick={() => void forget()}>Forget</TextAction>
          </span>
        ) : (
          <form className="box-line-row" onSubmit={(event) => void save(event)}>
            <Input value={typed} placeholder={sandboxNumbers[0] ?? "+15550100000"} aria-label="The test line" onChange={(event) => setTyped(event.target.value)} />
            <Button kind="primary" size="form" type="submit" disabled={move.busy || typed.trim() === ""}>
              Make it the test line
            </Button>
          </form>
        )}
        <Refused>{move.refused ?? line.refused}</Refused>
      </div>
    </Card>
  );
}
