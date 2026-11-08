/** An app's releases, newest first, and the way back to any but the one serving. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../lib/format";
import { ConfirmButton } from "./confirm";
import { readReleases, rollBack, whoIs, type Hosted, type Release } from "./door";
import { kilobytes } from "./fold";

export function Releases({ app, names, onRolledBack }: { app: Hosted; names: ReadonlyMap<string, string>; onRolledBack: () => void }): ReactNode {
  const credentials = useCredentials();
  const [releases, setReleases] = useState<Release[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    setReleases(null);
    readReleases(credentials, app.name).then(
      (read) => !gone && setReleases(read),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, app.name]);

  const back = async (release: number): Promise<void> => {
    setRefused(null);
    try {
      const made = await rollBack(credentials, app.name, release);
      setReleases((was) => [made, ...(was ?? [])]);
      onRolledBack();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <section className="dash-card" aria-label="Releases">
      <div className="dash-card-top">
        <span className="dash-eyebrow">Releases</span>
      </div>
      {refused !== null && <p className="app-refused">{refused}</p>}
      {releases === null ? (
        <p className="dash-quiet">Reading the releases…</p>
      ) : releases.length === 0 ? (
        <p className="dash-quiet">No release yet.</p>
      ) : (
        <div className="dash-rows">
          {releases.slice(0, 8).map((one) => (
            <div key={one.release} className="app-release dash-row" title={`sha256 ${one.sha256}`}>
              <span className="app-release-n">{one.release}</span>
              <span className="app-release-words">
                <span className="dash-clip">{one.note === "" ? "No note" : one.note}</span>
                <span className="dash-quiet dash-clip">
                  {whoIs(names, one.author)}, {ago(one.created_at)}, {kilobytes(one.bytes)}
                </span>
              </span>
              {one.release === app.live_release ? <span className="app-serving">Serving</span> : <ConfirmButton label="Roll back" asks="Sure?" onConfirm={() => void back(one.release)} />}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
