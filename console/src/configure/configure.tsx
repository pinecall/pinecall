/** Configure: how long a turn takes and what it costs off its real calls, the transcriber, model and voice, a Studio agent's greeting and prompt, and everything else it is set to. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useInsights } from "../lib/insights";
import { readLexicon, readReport, readSettings, setLexicon, setSettings, type LexiconAnswer, type LexiconBody, type Report, type TuningAnswer, type TuningBody } from "./door";
import { readJudging, type JudgingSettings } from "../judges/door";
import { cornerOf, nextRow, READ_ONLY, tunedIn, wholeFrom } from "./corner";
import { MeasuresCard, measuringOf } from "./measures-card";
import { Melody } from "./melody";
import { AppGreeting, StudioBrief } from "./prompt";
import { SettingsList } from "./settings-list";
import { Stages } from "./stages";
import "./configure.css";

const NO_WORDS: LexiconBody = { said: [], heard: [] };

export function Configure({ agent, kind, onSaved }: { agent: string; kind: "code" | "studio"; onSaved: () => void }): ReactNode {
  const credentials = useCredentials();
  const counted = useInsights(30, { agent });
  const rehearsed = useInsights(30, { agent, world: "sandbox" });
  const [report, setReport] = useState<Report | null>(null);
  const [answer, setAnswer] = useState<TuningAnswer | null>(null);
  const [lexicon, setLexiconAnswer] = useState<LexiconAnswer | null>(null);
  const [judging, setJudging] = useState<JudgingSettings | null>(null);
  // In the sandbox a person tunes their own corner; the team's is the base under it, and the CLI's to move.
  const team = false;
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [away, setAway] = useState<string | null>(null);

  const readAll = useCallback(async (): Promise<void> => {
    const [nextAnswer, nextReport] = await Promise.all([readSettings(credentials, agent), readReport(credentials, agent)]);
    setAnswer(nextAnswer);
    setReport(nextReport);
  }, [credentials, agent]);

  useEffect(() => {
    let gone = false;
    readAll().catch((failed: unknown) => !gone && setAway(saidBy(failed)));
    readLexicon(credentials, agent).then((read) => !gone && setLexiconAnswer(read), () => undefined);
    // The organization's judge is what judges an agent that names none; a key that cannot read it is told less.
    readJudging(credentials).then((read) => !gone && setJudging(read), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, agent, readAll]);

  const tuned = useMemo(() => (answer === null ? null : tunedIn(answer, team)), [answer, team]);
  const config: TuningBody = tuned?.config ?? {};

  // Only what was changed moves: the corner keeps its own knobs, and what it inherits from the team stays inherited.
  const save = async (changed: Partial<TuningBody>, drop: readonly (keyof TuningBody)[] = []): Promise<boolean> => {
    if (tuned === null) return false;
    setSaving(true);
    setRefused(null);
    try {
      await setSettings(credentials, agent, { config: nextRow(tuned, changed, drop), if_version: tuned.version, note: null, team });
      await readAll();
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveLexicon = async (words: LexiconBody): Promise<boolean> => {
    if (lexicon === null) return false;
    setSaving(true);
    setRefused(null);
    try {
      setLexiconAnswer(await setLexicon(credentials, agent, words, cornerOf(lexicon, team).standing?.version ?? null, team));
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    } finally {
      setSaving(false);
    }
  };

  if (away !== null) return <p className="cfg-refused">{away}</p>;
  if (report === null || answer === null) return <p className="dash-quiet">Reading what it runs on…</p>;

  const measuring = measuringOf(agent, report, counted, rehearsed);
  const lexiconCorner = lexicon === null ? null : cornerOf(lexicon, team).inEffect;
  const greetingLocked = answer.fixed.includes("greeting");
  const readOnly = READ_ONLY;
  const stagesProps = { readOnly, report, config, fixed: new Set(answer.fixed), saving, refused, onSave: save, onOpened: () => setRefused(null), onKept: readAll };

  return (
    <div className="cfg">
      {kind === "studio" && <MeasuresCard report={report} measuring={measuring} />}
      <Stages {...stagesProps} measured={measuring.measured} />
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      {kind === "studio" && <StudioBrief agent={agent} onSaved={onSaved} />}
      {kind === "code" && (
        <AppGreeting
          key={team ? "team" : "yours"}
          kept={readOnly ? report.greeting : greetingLocked ? report.greeting : config.greeting}
          locked={greetingLocked}
          readOnly={readOnly}
          saving={saving}
          refused={refused}
          onSave={(greeting) => (greeting == null ? save({}, ["greeting"]) : save({ greeting: { say: greeting.say, reply: greeting.reply, allow_interruptions: config.greeting?.allow_interruptions } }))}
        />
      )}
      <Melody key={agent} agent={agent} readOnly={readOnly} />
      <SettingsList {...stagesProps} answer={answer} lexicon={lexiconCorner?.lexicon ?? (lexicon === null ? null : NO_WORDS)} lexiconFrom={lexicon === null ? "pinecall" : wholeFrom(lexicon)} lexiconFixed={new Set(lexicon?.fixed ?? [])} judging={judging} onSaveLexicon={saveLexicon} />
    </div>
  );
}
