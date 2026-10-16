/** Observability: the window at a glance and day by day — latency, success, duration, endings, judges, tools, cost — every agent's or the one in view. */

import { useMemo, type ReactNode } from "react";
import { useParams } from "react-router";

import { useInsights, useWindowDays, windowSaid, WindowPicker } from "../../lib/insights";
import { useSeries, type SeriesDay } from "../../lib/series";
import { Card, CardHead, Empty, Page, PageHead, Stat, Stats, TableHead } from "../../ui";
import { Bars, type Stack } from "./bars";
import { Lines, type Line } from "./lines";
import "./observability.css";

const STAGE_NAME: Record<string, string> = { stt: "Transcription", llm: "First token", tts: "First audio" };
const BY_AGENT = "minmax(0,1.4fr) 90px 110px 110px 100px";

const seconds = (value: number): string => (value >= 10 ? `${Math.round(value)}s` : `${(Math.round(value * 100) / 100).toFixed(2)}s`);
const percent = (value: number): string => `${Math.round(value * 100)}%`;
const count = (value: number): string => `${Math.round(value)}`;
const dollars = (value: number): string => `$${value.toFixed(2)}`;
const reasonSaid = (reason: string): string => reason.replaceAll("_", " ");

function stageOf(day: SeriesDay, stage: string): SeriesDay["stages"][number] | undefined {
  return day.stages.find((one) => one.stage === stage);
}

/** The window's totals, what the cards at the top say. */
interface Totals {
  calls: number;
  held: number;
  judged: number;
  ttft: number | null;
  length: number | null;
  spend: number;
}

function totalsOf(rows: readonly SeriesDay[]): Totals {
  const calls = rows.reduce((sum, day) => sum + day.calls, 0);
  const held = rows.reduce((sum, day) => sum + day.judges.reduce((inner, judge) => inner + judge.held, 0), 0);
  const judged = rows.reduce((sum, day) => sum + day.judges.reduce((inner, judge) => inner + judge.judged, 0), 0);
  const ttfts = rows.flatMap((day) => {
    const llm = stageOf(day, "llm");
    return llm?.median_s === null || llm?.median_s === undefined ? [] : [{ value: llm.median_s, turns: llm.turns }];
  });
  const turns = ttfts.reduce((sum, one) => sum + one.turns, 0);
  const ttft = turns === 0 ? null : ttfts.reduce((sum, one) => sum + one.value * one.turns, 0) / turns;
  const finished = rows.filter((day) => day.mean_length_s !== null);
  const weight = finished.reduce((sum, day) => sum + day.finished, 0);
  const length = weight === 0 ? null : finished.reduce((sum, day) => sum + (day.mean_length_s ?? 0) * day.finished, 0) / weight;
  return { calls, held, judged, ttft, length, spend: rows.reduce((sum, day) => sum + day.spend_usd, 0) };
}

function utcDay(at: number): string {
  return new Date(at * 1000).toISOString().slice(0, 10);
}

function change(now: number, before: number): { text: string; tone: "up" | "down" | "flat" } | null {
  if (before === 0) return null;
  const moved = Math.round(((now - before) / before) * 100);
  return { text: moved === 0 ? "steady" : `${moved > 0 ? "+" : "−"}${Math.abs(moved)}%`, tone: moved === 0 ? "flat" : moved > 0 ? "up" : "down" };
}

/** Every number is the gateway's count over whole UTC days; a day nobody called is a gap, not a zero. */
export function Observability(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const asked = agent === "" ? undefined : agent;
  const [range, pickRange] = useWindowDays(7);
  const answered = useSeries({ agent: asked, days: range });
  const earlier = useSeries({ agent: asked, days: range, day: utcDay(Date.now() / 1000 - range * 86400) });
  const insights = useInsights({ agent: asked, days: range });
  const series = answered?.days === range ? answered.series : null;
  const days = useMemo(() => (series ?? []).map((day) => day.day), [series]);
  const rows = useMemo(() => series ?? [], [series]);
  const now = useMemo(() => totalsOf(rows), [rows]);
  const before = useMemo(() => totalsOf(earlier?.days === range ? earlier.series : []), [earlier, range]);
  const said = `vs the ${range} d before`;

  const latency: Line[] = useMemo(
    () => [
      { name: "End to end, median", values: rows.map((day) => day.e2e_median_s), tone: 1 },
      { name: "End to end, p95", values: rows.map((day) => day.e2e_p95_s), tone: 2 },
    ],
    [rows],
  );
  const stages: Line[] = useMemo(
    () => (["stt", "llm", "tts"] as const).map((stage, at): Line => ({ name: `${STAGE_NAME[stage]}, median`, values: rows.map((day) => stageOf(day, stage)?.median_s ?? null), tone: (at + 1) as 1 | 2 | 3 })),
    [rows],
  );
  const tails: Line[] = useMemo(
    () => (["stt", "llm", "tts"] as const).map((stage, at): Line => ({ name: `${STAGE_NAME[stage]}, p95`, values: rows.map((day) => stageOf(day, stage)?.p95_s ?? null), tone: (at + 1) as 1 | 2 | 3 })),
    [rows],
  );
  const judgeNames = useMemo(() => [...new Set(rows.flatMap((day) => day.judges.map((judge) => judge.name)))].sort(), [rows]);
  const judges: Line[] = useMemo(
    () =>
      judgeNames.slice(0, 4).map((name, at): Line => ({
        name,
        values: rows.map((day) => {
          const judge = day.judges.find((one) => one.name === name);
          return judge === undefined || judge.judged === 0 ? null : judge.held / judge.judged;
        }),
        tone: ((at % 4) + 1) as 1 | 2 | 3 | 4,
      })),
    [rows, judgeNames],
  );
  const failures = useMemo(() => {
    const broken = new Map<string, { broken: number; judged: number }>();
    for (const day of rows)
      for (const judge of day.judges) {
        const was = broken.get(judge.name) ?? { broken: 0, judged: 0 };
        broken.set(judge.name, { broken: was.broken + (judge.judged - judge.held), judged: was.judged + judge.judged });
      }
    return [...broken].filter(([, one]) => one.broken > 0).sort((a, b) => b[1].broken - a[1].broken);
  }, [rows]);
  const duration: Line[] = useMemo(() => [{ name: "Mean length", values: rows.map((day) => day.mean_length_s), tone: 1 }], [rows]);
  const calls: Line[] = useMemo(
    () => [
      { name: "Calls", values: rows.map((day) => (day.calls === 0 ? null : day.calls)), tone: 1 },
      { name: "A person took over", values: rows.map((day) => (day.calls === 0 ? null : day.escalated)), tone: 3 },
    ],
    [rows],
  );
  const tools: Line[] = useMemo(
    () => [
      { name: "Tools ran", values: rows.map((day) => (day.calls === 0 ? null : day.tools_ran)), tone: 1 },
      { name: "Tools that failed", values: rows.map((day) => (day.calls === 0 ? null : day.tools_failed)), tone: 3 },
    ],
    [rows],
  );
  const spend: Line[] = useMemo(() => [{ name: "Spend", values: rows.map((day) => (day.calls === 0 ? null : day.spend_usd)), tone: 4 }], [rows]);
  const endings = useMemo(() => {
    const totals = new Map<string, number>();
    for (const day of rows) for (const ending of day.endings) totals.set(ending.reason, (totals.get(ending.reason) ?? 0) + ending.count);
    const keys = [...totals].sort((a, b) => b[1] - a[1]).map(([reason]) => reason);
    const stacks: Stack[] = rows.map((day) => ({ day: day.day, counts: Object.fromEntries(day.endings.map((ending) => [ending.reason, ending.count])) }));
    return { keys, stacks };
  }, [rows]);
  const byAgent = useMemo(() => (insights?.agents ?? []).slice().sort((a, b) => b.calls - a.calls), [insights]);

  const moved = change(now.calls, before.calls);
  const heldNow = now.judged === 0 ? null : now.held / now.judged;
  const heldBefore = before.judged === 0 ? null : before.held / before.judged;
  const points = heldNow === null || heldBefore === null ? null : Math.round((heldNow - heldBefore) * 100);
  const faster = now.ttft === null || before.ttft === null ? null : before.ttft - now.ttft;

  return (
    <Page>
      <PageHead
        title="Observability"
        lede={`How ${agent === "" ? "every agent" : agent} ran over ${windowSaid(range)}: how fast each stage answered, how calls ended, what the judges held, which tools failed, what it cost — at a glance, then day by day.`}
        actions={<WindowPicker days={range} onPick={pickRange} />}
      />
      <Stats min={170}>
        <Stat size="big" label="Calls" value={now.calls} delta={moved?.text ?? said} tone={moved?.tone ?? "flat"} />
        <Stat
          size="big"
          label="Success rate"
          value={heldNow === null ? "—" : percent(heldNow)}
          delta={points === null ? (now.judged === 0 ? "nothing judged" : said) : points === 0 ? "steady" : `${points > 0 ? "+" : "−"}${Math.abs(points)} pts`}
          tone={points === null || points === 0 ? "flat" : points > 0 ? "up" : "down"}
        />
        <Stat
          size="big"
          label="Time to first token"
          value={now.ttft === null ? "—" : seconds(now.ttft)}
          delta={faster === null ? said : Math.abs(faster) < 0.05 ? "steady" : `${faster > 0 ? "−" : "+"}${Math.abs(faster).toFixed(2)}s`}
          tone={faster === null || Math.abs(faster) < 0.05 ? "flat" : faster > 0 ? "up" : "down"}
        />
        <Stat size="big" label="Mean length" value={now.length === null ? "—" : seconds(now.length)} delta={before.length === null ? said : `${seconds(before.length)} before`} tone="flat" />
        <Stat size="big" label="Spend" value={dollars(now.spend)} delta={before.spend === 0 ? said : `${dollars(before.spend)} before`} tone="flat" />
      </Stats>
      {series !== null && rows.every((day) => day.calls === 0) && <Empty>No call in {windowSaid(range)}. The charts fill in as calls come.</Empty>}
      <div className="obs-grid">
        <Card pad>
          <CardHead title="Latency, end to end" meta="from the caller's last word to the agent's first" />
          <Lines days={days} lines={latency} says={seconds} label="End-to-end latency a day" />
        </Card>
        <Card pad>
          <CardHead title="Latency by stage, median" meta="transcription, first token, first audio" />
          <Lines days={days} lines={stages} says={seconds} label="Median latency by stage a day" />
        </Card>
        <Card pad>
          <CardHead title="Latency by stage, p95" meta="the slow tail" />
          <Lines days={days} lines={tails} says={seconds} label="p95 latency by stage a day" />
        </Card>
        <Card pad>
          <CardHead title="Success rate by judge" meta="the share of verdicts each judge held" />
          <Lines days={days} lines={judges} says={percent} label="Held rate by judge a day" ceiling={1} />
        </Card>
        <Card pad>
          <CardHead title="How calls ended" meta="a day at a time, by reason" />
          <Bars stacks={endings.stacks} keys={endings.keys} label="Call endings a day" said={reasonSaid} />
        </Card>
        <Card pad>
          <CardHead title="Duration" meta="the mean length of the calls that ended" />
          <Lines days={days} lines={duration} says={seconds} label="Mean call length a day" />
        </Card>
        <Card pad>
          <CardHead title="Calls" meta="and how many a person took over" />
          <Lines days={days} lines={calls} says={count} label="Calls a day" />
        </Card>
        <Card pad>
          <CardHead title="Tools" meta="runs, and the ones that answered an error" />
          <Lines days={days} lines={tools} says={count} label="Tool runs and failures a day" />
        </Card>
        <Card pad>
          <CardHead title="Spend" meta="every vendor, in US dollars" />
          <Lines days={days} lines={spend} says={dollars} label="Spend a day" />
        </Card>
        <Card pad>
          <CardHead title="Failure modes" meta="the judges that said no, most often first" />
          {failures.length === 0 ? (
            <p className="obs-quiet">No judge said no in {windowSaid(range)}.</p>
          ) : (
            <div className="obs-endings">
              {failures.map(([name, one]) => (
                <div key={name} className="obs-ending">
                  <span className="ui-fixed">{name}</span>
                  <span className="obs-ending-count">
                    {one.broken} of {one.judged} · {percent(one.broken / one.judged)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      {agent === "" && byAgent.length > 0 && (
        <Card>
          <CardHead title="By agent" meta={windowSaid(range)} />
          <TableHead columns={BY_AGENT} labels={["Agent", "Calls", "Success rate", "Spend", "Per minute"]} />
          {byAgent.map((one) => (
            <div key={one.slug} className="ui-table-row" style={{ gridTemplateColumns: BY_AGENT }}>
              <span className="ui-cell-strong ui-clip">{one.slug}</span>
              <span className="ui-cell-ink">{one.calls}</span>
              <span className="ui-cell-ink">{one.score === null ? "—" : percent(one.score)}</span>
              <span className="ui-cell-ink">{dollars(one.spend.llm_usd + one.spend.stt_usd + one.spend.tts_usd + one.spend.phone_usd + one.spend.platform_usd)}</span>
              <span className="ui-cell-faint">{one.spend.per_minute_usd === null ? "—" : `$${one.spend.per_minute_usd.toFixed(3)}`}</span>
            </div>
          ))}
        </Card>
      )}
    </Page>
  );
}
