/** Studio in the sandbox: the agent's definition as a form on the left — saved, deployed, downloaded — and the agent to talk to on the right. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { GatewayError, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { Button, PageHead, Refused } from "../../ui";
import { readSecrets } from "../secrets";
import { Collection } from "./collect";
import { deployStudioAgent, readCode, readStudioAgent, saveStudioAgent, type Definition, type StudioAgent } from "./door";
import { changed } from "./draft";
import { GreetingSection, Instructions } from "./instructions";
import { Preview } from "./preview";
import { Tools } from "./tools";

const CONFLICT = 409;

/** What the editor is doing, so one button at a time says so. */
type Busy = "saving" | "deploying" | "downloading" | "reloading" | null;

export function Editor({ initial }: { initial: StudioAgent }): ReactNode {
  const credentials = useCredentials();
  const [read, setRead] = useState(initial);
  const [draft, setDraft] = useState<Definition>(initial.definition);
  const [secrets, setSecrets] = useState<string[]>([]);
  const [busy, setBusy] = useState<Busy>(null);
  const [refused, setRefused] = useState<string | null>(null);
  // Somebody saved over the release this page read: the next save waits for a reload.
  const [stale, setStale] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const name = read.name;
  const dirty = changed(draft, read.definition);

  useEffect(() => {
    let gone = false;
    readSecrets(credentials).then(
      (listed) => {
        if (!gone) setSecrets(listed.map((one) => one.name));
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const doing = async (what: Exclude<Busy, null>, work: () => Promise<void>): Promise<void> => {
    setBusy(what);
    setRefused(null);
    setSaid(null);
    try {
      await work();
    } catch (failed) {
      if (failed instanceof GatewayError && failed.status === CONFLICT) setStale(true);
      setRefused(saidBy(failed));
    } finally {
      setBusy(null);
    }
  };

  const save = (): Promise<void> =>
    doing("saving", async () => {
      const saved = await saveStudioAgent(credentials, name, draft, read.release);
      setRead(saved);
      setDraft(saved.definition);
      setSaid(`Saved as release ${saved.release}.`);
    });

  const reload = (): Promise<void> =>
    doing("reloading", async () => {
      const now = await readStudioAgent(credentials, name);
      setRead(now);
      setDraft(now.definition);
      setStale(false);
    });

  const deploy = (): void => {
    const unsaved = dirty ? " The changes on this page that are not saved are not part of it." : "";
    if (!window.confirm(`Deploy release ${read.release} of ${name} to production? Production's calls answer with it from the next call.${unsaved}`)) return;
    void doing("deploying", async () => {
      const production = await deployStudioAgent(credentials, name, read.release);
      setSaid(`Production answers with release ${production.release}.`);
    });
  };

  const download = (): Promise<void> =>
    doing("downloading", async () => {
      const zip = await readCode(credentials, name);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(zip);
      link.download = `${name}.zip`;
      link.click();
      // Revoked once the browser has taken the download: revoked at once, some abort it.
      setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
    });

  const edit = (part: Partial<Definition>): void => setDraft((was) => ({ ...was, ...part }));

  return (
    <div className="sto-grid">
      <div className="sto-form">
        <PageHead
          title={name}
          lede={
            <>
              Release {read.release} · saved by {read.author} · {dayAndTime(read.saved_at)}
              {read.stopped ? " · stopped" : ""}
              {dirty ? " · unsaved changes" : ""}
            </>
          }
          actions={
            <>
              <Button size="md" onClick={() => void download()} disabled={busy !== null}>
                {busy === "downloading" ? "Downloading…" : "Download code"}
              </Button>
              <Button size="md" onClick={deploy} disabled={busy !== null}>
                {busy === "deploying" ? "Deploying…" : "Deploy to production"}
              </Button>
              <Button size="md" kind="primary" onClick={() => void save()} disabled={busy !== null || !dirty || stale}>
                {busy === "saving" ? "Saving…" : "Save"}
              </Button>
            </>
          }
        />
        <p className="sto-hint">
          Voice and models: <Link to={`/a/${encodeURIComponent(name)}/configure`}>Configure</Link>
        </p>
        <Refused>{refused}</Refused>
        {stale && (
          <div>
            <Button size="sm" onClick={() => void reload()} disabled={busy !== null}>
              {busy === "reloading" ? "Reloading…" : "Reload"}
            </Button>
          </div>
        )}
        {said !== null && <p className="sto-said">{said}</p>}
        <Instructions text={draft.instructions} onChange={(instructions) => edit({ instructions })} />
        <GreetingSection greeting={draft.greeting} onChange={(greeting) => edit({ greeting })} />
        <Tools agent={name} definition={draft} secrets={secrets} onChange={(tools) => edit({ tools })} />
        <Collection collect={draft.collect} secrets={secrets} onChange={(collect) => edit({ collect })} />
      </div>
      <Preview agent={name} />
    </div>
  );
}
