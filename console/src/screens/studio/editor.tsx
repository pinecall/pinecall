/** Studio in the sandbox: the agent's definition in tabs on the left — saved, downloaded, its cases under it — and on the right the agent to try, with the way to deploy it under it. */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { GatewayError, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { asking, type TestValues } from "../../lib/test-values";
import { Button, Icon, Page, Refused, Tabs } from "../../ui";
import { readSecrets } from "../secrets";
import { TestValuesTab } from "../settings";
import { Collection } from "./collect";
import { deployStudioAgent, readCode, readStudioAgent, saveStudioAgent, type Definition, type StudioAgent } from "./door";
import { changed } from "./draft";
import { Head } from "./head";
import { GreetingSection, Instructions } from "./instructions";
import { Live, productionSaid } from "./live";
import { TestSection } from "./test";
import { Tip } from "./tip";
import { Tools } from "./tools";
import { TryIt } from "./try-it";

const CONFLICT = 409;

/** The four tabs of the definition, and the voice and models the room beside is tried with. */
type Tab = "instructions" | "greeting" | "tools" | "collect" | "voice";

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
  // What production holds, read from here: undefined while asked, null when it holds nothing of this agent's or is not ours to read.
  const [production, setProduction] = useState<StudioAgent | null | undefined>(undefined);
  // Starting the chat over remounts it: another room, another conversation.
  const [round, setRound] = useState(0);
  // The voice and models the room being tried runs on, other than the agent's own: asked for here, kept nowhere.
  const [tried, setTried] = useState<TestValues | null>(null);
  const [params, setParams] = useSearchParams();
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

  useEffect(() => {
    let gone = false;
    readStudioAgent({ ...credentials, world: "production" }, name).then(
      (held) => {
        if (!gone) setProduction(held);
      },
      () => {
        if (!gone) setProduction(null);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, name]);

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
      const deployed = await deployStudioAgent(credentials, name, read.release);
      setProduction(deployed);
      setSaid(`Production answers with release ${deployed.release}.`);
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

  const tabs = [
    { tab: "instructions" as const, name: "Instructions", icon: <Icon name="words" size={15} /> },
    { tab: "greeting" as const, name: "Greeting", icon: <Icon name="chat" size={15} /> },
    { tab: "tools" as const, name: "Tools", icon: <Icon name="plug" size={15} />, mark: draft.tools.length === 0 ? undefined : <span className="sto-tab-mark">{draft.tools.length}</span> },
    { tab: "collect" as const, name: "Data collection", icon: <Icon name="clipboard" size={15} />, mark: draft.collect === null || draft.collect === undefined ? undefined : <span className="sto-tab-mark">On</span> },
    { tab: "voice" as const, name: "Voice & models", icon: <Icon name="sliders" size={15} />, mark: asking(tried) ? <span className="sto-tab-mark">Test</span> : undefined },
  ];
  const asked = params.get("tab");
  const tab: Tab = tabs.some((one) => one.tab === asked) ? (asked as Tab) : "instructions";

  return (
    <div className="sto-grid">
      <div className="sto-form">
        <Page>
          <Head
            name={name}
            sub={[`Release ${read.release} · saved by ${read.author} · ${dayAndTime(read.saved_at)}`, read.stopped ? "stopped" : "", productionSaid(read.release, production), dirty ? "unsaved changes" : ""].filter((one) => one !== "").join(" · ")}
            busy={busy !== null}
            downloading={busy === "downloading"}
            saving={busy === "saving"}
            canSave={dirty && !stale}
            live={<Live release={read.release} production={production} busy={busy === "deploying"} onDeploy={deploy} />}
            onDownload={() => void download()}
            onSave={() => void save()}
          />
          <Refused>{refused}</Refused>
          {stale && (
            <div>
              <Button size="sm" onClick={() => void reload()} disabled={busy !== null}>
                {busy === "reloading" ? "Reloading…" : "Reload"}
              </Button>
            </div>
          )}
          {said !== null && <p className="sto-said">{said}</p>}
          <div className="sto-tabs">
            <Tabs label="The agent's definition" tabs={tabs} on={tab} onPick={(picked) => setParams(picked === "instructions" ? {} : { tab: picked })} />
          </div>
          {tab === "instructions" && <Instructions text={draft.instructions} onChange={(instructions) => edit({ instructions })} tip={<Tip agent={name} />} />}
          {tab === "greeting" && <GreetingSection greeting={draft.greeting} onChange={(greeting) => edit({ greeting })} />}
          {tab === "tools" && <Tools agent={name} definition={draft} secrets={secrets} onChange={(tools) => edit({ tools })} />}
          {tab === "collect" && <Collection collect={draft.collect} secrets={secrets} onChange={(collect) => edit({ collect })} />}
          {tab === "voice" && (
            <div className="sto-panel">
              <p className="sto-blurb">Try another voice or model in the chat on the right. Only that chat changes: {name}&apos;s saved settings stay as they are.</p>
              <TestValuesTab agent={name} values={tried} onApply={setTried} />
            </div>
          )}
          {/* Under the definition whichever tab is open: the agent's tests are its cases, played against the agent the gateway holds. */}
          <div className="sto-test">
            <TestSection agent={name} />
          </div>
        </Page>
      </div>
      <TryIt key={round} agent={name} release={read.release} values={tried} onReset={() => setRound((was) => was + 1)} />
    </div>
  );
}
