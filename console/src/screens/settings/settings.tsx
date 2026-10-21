/** Settings screen: the agent's versioned config per world and corner. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";

import { type TuningAnswer, type TuningBody, type TuningHistory } from "@pinecall/core/wire/rest-org";
import { type KnowledgeBase } from "@pinecall/core/wire/rest-retrieval";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "../../lib/mode";
import { useScopes } from "../../lib/whoami";
import { Empty, Page, PageHead, Refused, Segmented, usePane } from "../../ui";
import { readBases } from "../docs/door";
import { readPipeline, type Report } from "../pipeline/door";
import { readVendors } from "../providers";
import { edited, readHistory, readSettings, rollbackTo, setSettings } from "./door";
import { sectionsFor, SettingsForm, type Section } from "./form";
import { History } from "./history";
import { Now, type Corner } from "./now";
import type { Step } from "./pipeline";
import "./settings.css";

function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

const STEPS: readonly Step[] = ["hears", "decides", "speaks", "judged"];

// Production edits production's corner (the gateway enforces access); the sandbox edits yours, or
// the team's when picked. The open section, and the stage under the Pipeline's tiles, live in the URL.
export function Settings(): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const scopes = useScopes();
  const [params, setParams] = useSearchParams();
  const [answer, setAnswer] = useState<TuningAnswer | null>(null);
  const [history, setHistory] = useState<TuningHistory | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [bases, setBases] = useState<KnowledgeBase[] | null>(null);
  // The vendors this org runs on its own key; every other is lent by the runtime.
  const [own, setOwn] = useState<ReadonlySet<string>>(new Set());
  const [team, setTeam] = useState(false);
  const [saving, setSaving] = useState(false);
  // The save bar is the form's, drawn here under the page that scrolls.
  const [bar, setBar] = useState<HTMLElement | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const wordsOnly = scopes !== null && !scopes.includes("pipeline");
  const production = WORLD === "production";
  const offered = sectionsFor(wordsOnly);
  const asked = params.get("section");
  // A link from before the tiles named a stage as a section: it opens the Pipeline on that stage.
  const linked = STEPS.find((one) => one === asked);
  const section: Section = linked !== undefined && offered.some((one) => one.tab === "pipeline") ? "pipeline" : offered.some((one) => one.tab === asked) ? (asked as Section) : offered[0]!.tab;
  const step: Step = linked ?? STEPS.find((one) => one === params.get("stage")) ?? "hears";
  const pickStep = (picked: Step): void => setParams(picked === "hears" ? {} : { stage: picked });

  const reread = useCallback(async (): Promise<void> => {
    setAnswer(await readSettings(credentials, agent));
    setHistory(await readHistory(credentials, agent, production || team));
    // Cleared here, not at the top of the effect: otherwise a refused read leaves the screen stuck on
    // "Asking the gateway…".
    setRefused(null);
  }, [credentials, agent, team, production]);

  useEffect(() => {
    let gone = false;
    reread().catch((failed: unknown) => {
      if (!gone) setRefused(saidBy(failed));
    });
    // Vendors/models/voices come from the pipeline report, bases from knowledge; either may be refused.
    readPipeline(credentials, agent).then(
      (read) => !gone && setReport(read),
      (failed: unknown) => {
        if (!gone && !(failed instanceof GatewayError && (failed.status === 403 || failed.status === 404))) setRefused(saidBy(failed));
      },
    );
    readBases(credentials).then(
      (read) => !gone && setBases(read.bases),
      () => !gone && setBases([]),
    );
    readVendors(credentials).then(
      (read) => !gone && setOwn(new Set(read)),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, reread]);

  // Re-read on focus so CLI changes (`pinecall agent set`) show up; a new version re-keys the form.
  useEffect(() => {
    const again = (): void => void reread().catch(() => undefined);
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [reread]);

  const save = async (config: TuningBody, ifVersion: number | null, note: string | null): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      setAnswer(await setSettings(credentials, agent, { config, if_version: ifVersion, note, team }));
      setHistory(await readHistory(credentials, agent, production || team));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  const rollBack = async (version: number): Promise<void> => {
    setRefused(null);
    try {
      setAnswer(await rollbackTo(credentials, agent, version, production || team));
      setHistory(await readHistory(credentials, agent, production || team));
      setSaid(`v${version} is the newest again, as a new version.`);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const standing = answer === null ? null : edited(answer, production || team);
  // An empty personal corner runs on the team's, so the form opens on the team's config.
  const inEffect = standing ?? (answer === null || production || team ? null : answer.team);
  const pane = usePane({ name: "settings.now", initial: 340, min: 280, max: 560, side: "right" });
  const corners: readonly Corner[] = production ? ["production"] : ["yours", "team", "production"];

  return (
    <div className="set-grid" style={pane.style}>
      {pane.handle}
      <div className="set-column">
        <Page width={900}>
          <PageHead
            title="Configure"
            ledeWidth={660}
            lede={
              production
                ? "What this agent runs on in production. Every save is a new version with your name on it, and any version can be rolled back."
                : "What this agent runs on in the sandbox: yours to try in your own corner, or the team's, which every corner falls back to. Every save is a version; production has its own page."
            }
            actions={
              !wordsOnly && !production && (
                <div className="set-saving">
                  <span className="set-saving-label">Saving to</span>
                  <Segmented
                    options={[
                      { value: "yours", label: "Your corner" },
                      { value: "team", label: "Team" },
                    ]}
                    value={team ? "team" : "yours"}
                    onChange={(picked) => setTeam(picked === "team")}
                  />
                </div>
              )
            }
          />

          {answer === null && <Empty>{refused ?? "Asking the gateway…"}</Empty>}
          {answer !== null && (
            <div className="set-main">
              <SettingsForm
                // Re-key once vendors arrive: wire words are parsed as vendor or model against them.
                key={`${agent}-${team}-${standing?.version ?? 0}-${inEffect?.version ?? 0}-${report === null ? "asking" : "read"}-${answer.fixed.join(",")}`}
                standing={inEffect?.config ?? {}}
                version={standing?.version ?? null}
                wordsOnly={wordsOnly}
                language={report?.speaks.language ?? null}
                providers={report?.providers ?? []}
                defaults={report?.defaults ?? {}}
                models={report?.models ?? {}}
                runs={report?.runs ?? {}}
                realtime={report?.realtime ?? {}}
                bases={bases}
                fixed={new Set(answer.fixed)}
                running={report === null ? null : { hears: report.hears, decides: report.decides, speaks: report.speaks, talks: report.talks ?? null }}
                own={own}
                section={section}
                onPickSection={(picked) => setParams(picked === offered[0]!.tab ? {} : { section: picked })}
                step={step}
                onPickStep={pickStep}
                bar={bar}
                saving={saving}
                error={refused}
                onSave={save}
              />
            </div>
          )}

          {said !== null && <div className="ui-empty">{said}</div>}
          {/* Write refusals only; a refused read is already shown in place of the screen. */}
        {answer !== null && <Refused>{refused}</Refused>}
        </Page>
        <div ref={setBar} />
      </div>

      <aside className="set-pane" aria-label="what is set, and its history">
        {answer === null ? (
          <p className="set-pane-empty">Asking the gateway…</p>
        ) : (
          <>
            {/* Keyed like the form, so it follows the corner being edited. */}
            <Now key={team ? "team" : "yours"} answer={answer} corners={corners} first={production ? "production" : team ? "team" : "yours"} />
            <History kept={history} canRollBack={!wordsOnly} onRollBack={rollBack} />
          </>
        )}
      </aside>
    </div>
  );
}
