/** An app's releases, newest first, and a rollback to any but the one serving. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Empty, Pill, Refused, TableHead, TextAction } from "../../ui";
import { readReleases, rollBack, type Hosted, type Release } from "./door";

const COLUMNS = "72px minmax(0,1.4fr) minmax(0,1fr) 120px 90px 150px";

export function ReleasesPanel({ app, close, rolledBack }: { app: Hosted; close: () => void; rolledBack: () => void }): ReactNode {
  const credentials = useCredentials();
  const [releases, setReleases] = useState<Release[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readReleases(credentials, app.name).then(
      (read) => {
        if (!gone) setReleases(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, app.name]);

  const back = async (release: number): Promise<void> => {
    const next = (releases?.[0]?.release ?? app.release ?? release) + 1;
    if (!window.confirm(`Roll ${app.name} back to release ${release}? Release ${release}'s sources become release ${next}; the one serving keeps answering until it registers.`)) return;
    setRefused(null);
    try {
      const made = await rollBack(credentials, app.name, release);
      setReleases((was) => [made, ...(was ?? [])]);
      rolledBack();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Card>
      <CardHead title={`Releases · ${app.name}`} meta="newest first" action={<TextAction onClick={close}>Close</TextAction>} />
      <Refused>{refused}</Refused>
      {releases !== null && releases.length === 0 ? (
        <Empty>No release yet.</Empty>
      ) : (
        <>
          <TableHead columns={COLUMNS} labels={["Release", "Note", "Author", "Sent", "Size>", ""]} />
          {(releases ?? []).map((one) => (
            <div key={one.release} className="ui-table-row" style={{ gridTemplateColumns: COLUMNS }} title={`sha256 ${one.sha256}`}>
              <span className="ui-cell-strong ui-clip">{one.release}</span>
              <span className="ui-cell-ink ui-clip">{one.note === "" ? "—" : one.note}</span>
              <span className="ui-cell-ink ui-clip">{one.author}</span>
              <span className="ui-cell-faint">{dayAndTime(one.created_at)}</span>
              <span className="ui-cell-faint ui-cell-right apps-hours">{kilobytes(one.bytes)}</span>
              <span className="ui-cell-end">
                {one.release === app.live_release ? (
                  <Pill tone="green">serving</Pill>
                ) : (
                  <TextAction onClick={() => void back(one.release)}>Roll back to this</TextAction>
                )}
              </span>
            </div>
          ))}
        </>
      )}
    </Card>
  );
}

function kilobytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
