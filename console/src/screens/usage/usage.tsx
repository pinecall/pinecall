/** Usage screen: provider costs by day, agent and call, as logged. */

import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime, today, usd } from "../../lib/format";
import { useInsights } from "../../lib/insights";
import { Minutes, minutesMeter, useLimits } from "../../lib/limits";
import { Bar, Card, CardFoot, Empty, Page, PageHead, Refused, Stat, Stats, TableHead, TableRow, Tabs } from "../../ui";
import { readUsage, type UsageRow } from "./door";
import { byAgent, byCall, byDay, total, type Group } from "./folded";
import "./usage.css";

type Tab = "days" | "agents" | "calls";

const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "days", name: "By day" },
  { tab: "agents", name: "By agent" },
  { tab: "calls", name: "Call by call" },
];

const GROUP_COLUMNS = "minmax(0,1.2fr) 70px 80px 90px minmax(0,1fr) 90px";
const CALL_COLUMNS = "130px 140px minmax(0,1fr) 70px 80px 90px";

// Read all pages so totals are complete, capped as a safety limit.
const PAGES_AT_MOST = 40;

/** All of the org's metered rows, folded one line per call; totals are summed client-side. */
export function Usage(): ReactNode {
  const credentials = useCredentials();
  const insights = useInsights();
  const meter = minutesMeter(useLimits());
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some((one) => one.tab === params.get("tab")) ? (params.get("tab") as Tab) : "days";
  const [rows, setRows] = useState<UsageRow[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    void (async () => {
      try {
        const read: UsageRow[] = [];
        let after = 0;
        for (let page = 0; page < PAGES_AT_MOST; page += 1) {
          const answer = await readUsage(credentials, after);
          if (gone) return;
          read.push(...answer.rows);
          setRows([...read]);
          if (answer.next === null) break;
          after = answer.next;
        }
      } catch (failed) {
        if (!gone) setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      }
    })();
    return () => {
      gone = true;
    };
  }, [credentials]);

  const bills = byCall(rows ?? []);
  const all = total(bills);
  const days = byDay(bills);
  const spentToday = days.find((day) => day.name === today().today)?.cost_usd ?? 0;
  const budget = insights?.budget ?? null;

  return (
    <Page tight>
      <PageHead title="Usage" lede="What this org spent: the providers' bill as the call log knows it, never a price of ours." />
      <Refused>{refused}</Refused>

      {rows !== null && (
        <Stats min={150}>
          <Stat
            size="small"
            label={budget !== null ? "Spent this month" : "Spent in all"}
            value={usd(budget !== null ? budget.spent_usd_month : all.cost_usd)}
            of={budget !== null && budget.limit_usd !== null ? `of ${usd(budget.limit_usd)}` : undefined}
            accent
          />
          {meter !== null && <Minutes meter={meter} size="small" />}
          <Stat size="small" label="Today" value={usd(spentToday)} />
          <Stat size="small" label="Calls" value={all.calls} />
          <Stat size="small" label="Minutes" value={all.minutes.toFixed(1)} />
          <Stat size="small" label="Evals" value={all.evals} />
          <Stat size="small" label="Simulations" value={all.simulations} />
          <Stat size="small" label="Per call" value={all.calls === 0 ? "—" : usd(all.cost_usd / all.calls)} />
          <Stat size="small" label="Per minute" value={all.minutes === 0 ? "—" : usd(all.cost_usd / all.minutes)} />
        </Stats>
      )}

      <Tabs label="Usage" tabs={TABS} on={tab} onPick={(picked) => setParams(picked === "days" ? {} : { tab: picked })} />

      {rows !== null && bills.length === 0 && (
        <Card>
          <Empty>Nothing metered yet: the first call to end writes the first row.</Empty>
        </Card>
      )}

      {bills.length > 0 && tab !== "calls" && <Groups label={tab === "days" ? "Day" : "Agent"} groups={tab === "days" ? days : byAgent(bills)} />}

      {bills.length > 0 && tab === "calls" && (
        <Card>
          <TableHead columns={CALL_COLUMNS} labels={["Started", "Agent", "Call", "Min>", "Messages>", "Cost>"]} />
          {bills.map((bill) => (
            <TableRow key={bill.call} columns={CALL_COLUMNS}>
              <span className="ui-cell-faint">{dayAndTime(bill.at)}</span>
              <span className="ui-cell-ink ui-clip">{bill.agent}</span>
              <Link to={`/calls/${bill.call}`} className="usage-call ui-clip">
                {bill.call}
              </Link>
              <span className="ui-cell-ink usage-right">{bill.minutes.toFixed(1)}</span>
              <span className="ui-cell-ink usage-right">{bill.messages}</span>
              <span className="usage-cost">{usd(bill.cost_usd)}</span>
            </TableRow>
          ))}
          <CardFoot>
            <span>
              {bills.length} calls{all.judge_calls > 0 && ` · ${all.judge_calls} judge calls`} · a call's judging is folded into its line
            </span>
          </CardFoot>
        </Card>
      )}
    </Page>
  );
}

/** Spend per day or agent, with its share as a bar. */
function Groups({ label, groups }: { label: string; groups: Group[] }): ReactNode {
  const most = Math.max(...groups.map((group) => group.cost_usd), 0);
  return (
    <Card>
      <TableHead columns={GROUP_COLUMNS} labels={[label, "Calls>", "Min>", "Per call>", "", "Cost>"]} />
      {groups.map((group) => (
        <TableRow key={group.name} columns={GROUP_COLUMNS}>
          <span className="ui-cell-strong ui-clip">{group.name}</span>
          <span className="ui-cell-ink usage-right">{group.calls}</span>
          <span className="ui-cell-ink usage-right">{group.minutes.toFixed(1)}</span>
          <span className="ui-cell-faint usage-right">{usd(group.cost_usd / group.calls)}</span>
          <span className="usage-bar">
            <Bar share={most === 0 ? 0 : group.cost_usd / most} />
          </span>
          <span className="usage-cost">{usd(group.cost_usd)}</span>
        </TableRow>
      ))}
    </Card>
  );
}
