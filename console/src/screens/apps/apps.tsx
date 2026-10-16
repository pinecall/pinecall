/** Apps: the org's hosted apps in this world — their state, time served, and logs, releases, stop, start, remove. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useWorld } from "../../lib/world";
import { Card, Empty, Page, PageHead, Pill, Refused, TableHead, TextAction } from "../../ui";
import { readHosted, readServed, removeApp, startApp, stopApp, type Hosted } from "./door";
import { firstLine, hours, servedByApp, stateOf } from "./fold";
import { LogsPanel } from "./logs";
import { ReleasesPanel } from "./releases";
import "./apps.css";

const COLUMNS = "minmax(0,1fr) minmax(0,1.2fr) minmax(0,0.9fr) 96px 250px";

const CLI_DOCS = "https://docs.pinecall.io/cli/overview";

/** What is open under the list: one app's logs or its releases. */
type Opened = { name: string; what: "logs" | "releases" } | null;

/**
 * Every door here acts in this console's world and takes a key that opens `app`: a person whose
 * role has it sees the list, anyone else sees the gateway's refusal in its own words.
 */
export function Apps(): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const [apps, setApps] = useState<Hosted[] | null>(null);
  const [served, setServed] = useState<Map<string, number>>(new Map());
  const [opened, setOpened] = useState<Opened>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    setApps(await readHosted(credentials));
    setServed(servedByApp(await readServed(credentials)));
  }, [credentials]);

  useEffect(() => {
    let gone = false;
    readHosted(credentials).then(
      (held) => {
        if (!gone) setApps(held);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    readServed(credentials).then(
      (rows) => {
        if (!gone) setServed(servedByApp(rows));
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const act = async (doing: () => Promise<void>): Promise<void> => {
    setRefused(null);
    try {
      await doing();
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const stop = (name: string): void => {
    if (!window.confirm(`Stop ${name}? Its process drains; its releases and token stay.`)) return;
    void act(() => stopApp(credentials, name));
  };

  const remove = (name: string): void => {
    if (!window.confirm(`Remove ${name}? Every release of it goes, and its token is revoked. There is no undo.`)) return;
    if (opened?.name === name) setOpened(null);
    void act(() => removeApp(credentials, name));
  };

  const open = (name: string, what: "logs" | "releases"): void =>
    setOpened((was) => (was?.name === name && was.what === what ? null : { name, what }));

  const openApp = opened === null ? undefined : apps?.find((app) => app.name === opened.name);

  return (
    <Page tight>
      <PageHead
        title="Apps"
        ledeWidth={660}
        lede={`The agents this box runs for the org in ${world}, each from the sources a release uploaded. A release is never edited: a rollback sends an earlier one's sources again, as the next.`}
      />

      <Refused>{refused}</Refused>

      <Card>
        {apps !== null && apps.length === 0 ? (
          <Empty>
            No app is hosted in {world} yet. One is put here from a terminal, in the project's folder:{" "}
            <span className="ui-fixed">{world === "production" ? "pinecall deploy --prod" : "pinecall deploy"}</span> — with{" "}
            <span className="ui-fixed">--prod</span> it goes to production, without it to the sandbox. See{" "}
            <a href={CLI_DOCS} target="_blank" rel="noreferrer">
              the CLI
            </a>
            .
          </Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["App", "State", "Made by", "This month>", ""]} />
            {(apps ?? []).map((app) => (
              <Row
                key={app.name}
                app={app}
                seconds={served.get(app.name) ?? 0}
                opened={opened?.name === app.name ? opened.what : null}
                open={open}
                stop={stop}
                start={(name) => void act(() => startApp(credentials, name))}
                remove={remove}
              />
            ))}
          </>
        )}
      </Card>

      {opened !== null && opened.what === "logs" && <LogsPanel key={opened.name} name={opened.name} close={() => setOpened(null)} />}
      {opened !== null && opened.what === "releases" && openApp !== undefined && (
        <ReleasesPanel key={opened.name} app={openApp} close={() => setOpened(null)} rolledBack={() => void reread()} />
      )}
    </Page>
  );
}

/** One app: its name, its state (a failure opens to its whole reason), who made it, its hours, its actions. */
function Row({
  app,
  seconds,
  opened,
  open,
  stop,
  start,
  remove,
}: {
  app: Hosted;
  seconds: number;
  opened: "logs" | "releases" | null;
  open: (name: string, what: "logs" | "releases") => void;
  stop: (name: string) => void;
  start: (name: string) => void;
  remove: (name: string) => void;
}): ReactNode {
  const state = stateOf(app);
  return (
    <div className="apps-row">
      <div className="ui-table-row" style={{ gridTemplateColumns: COLUMNS }}>
        <span className="ui-cell-strong ui-clip">{app.name}</span>
        <span>
          <Pill tone={state.tone}>{state.text}</Pill>
        </span>
        <span className="ui-cell-ink ui-clip">{app.created_by}</span>
        <span className="ui-cell-faint ui-cell-right apps-hours">{hours(seconds)}</span>
        <span className="apps-actions">
          <TextAction onClick={() => open(app.name, "logs")}>{opened === "logs" ? "Hide logs" : "Logs"}</TextAction>
          <TextAction onClick={() => open(app.name, "releases")}>{opened === "releases" ? "Hide releases" : "Releases"}</TextAction>
          {app.stopped ? <TextAction onClick={() => start(app.name)}>Start</TextAction> : <TextAction onClick={() => stop(app.name)}>Stop</TextAction>}
          <TextAction danger onClick={() => remove(app.name)}>
            Remove
          </TextAction>
        </span>
      </div>
      {state.why !== null && (
        <details className="apps-why">
          <summary>{firstLine(state.why)}</summary>
          <pre className="ui-code">{state.why}</pre>
        </details>
      )}
    </div>
  );
}
