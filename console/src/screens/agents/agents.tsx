/** Overview screen: held agents, processes, numbers, tokens and vendors. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { READY, type Catalogue } from "../../lib/catalogue";
import { CORNERS, meIn, somebodyElses, through, whoseCorner, type Corners } from "../../lib/corners";
import { prettyNumber } from "@pinecall/core/calls";
import { ago, startedOn, today } from "../../lib/format";
import { has, ORG_SCREENS, WORLD } from "../../lib/mode";
import { useOrg } from "../../lib/org";
import { opens } from "@pinecall/core/scopes";
import { useScopes, useWhoami } from "../../lib/whoami";
import {
  Avatar,
  ButtonLink,
  Card,
  CardAction,
  CardFoot,
  CardHead,
  Chips,
  Dot,
  Empty,
  Item,
  Page,
  PageHead,
  Pill,
  Refused,
  Stat,
  Stats,
  TableHead,
  TableRow,
  Tag,
  tintAt,
} from "../../ui";
import { readTokens, type Listed } from "../tokens/door";
import { Processes } from "./processes";
import { readAvailable, readNumbers, type Answering } from "../numbers/door";
import { readCatalogue, readVendors } from "../providers/door";
import "./agents.css";

const COLUMNS = "minmax(0,1.5fr) minmax(0,1.3fr) minmax(0,1.1fr) 90px 90px";

/** Reads the other org doors, each only if the screen exists here and the key has the scope. */
interface Accounts {
  numbers: Answering[] | null;
  free: number | null;
  keys: Listed[] | null;
  catalogue: Catalogue | null;
  brought: string[];
}

function useAccounts(): Accounts {
  const credentials = useCredentials();
  const scopes = useScopes();
  const [accounts, setAccounts] = useState<Accounts>({ numbers: null, free: null, keys: null, catalogue: null, brought: [] });
  const may = (key: string): boolean => has(ORG_SCREENS, key) && scopes !== null && opens(scopes, key);
  const numbers = may("numbers");
  const keys = has(ORG_SCREENS, "tokens");
  const providers = may("providers");

  useEffect(() => {
    let gone = false;
    void (async () => {
      const [routes, available, listed, catalogue, brought] = await Promise.all([
        numbers ? readNumbers(credentials).catch(() => null) : Promise.resolve(null),
        numbers ? readAvailable(credentials).catch(() => null) : Promise.resolve(null),
        keys ? readTokens(credentials).catch(() => null) : Promise.resolve(null),
        providers ? readCatalogue(credentials).catch(() => null) : Promise.resolve(null),
        providers ? readVendors(credentials).catch(() => []) : Promise.resolve([]),
      ]);
      if (gone) return;
      setAccounts({
        numbers: routes,
        free: available === null ? null : available.numbers.filter((one) => !one.imported).length,
        keys: listed,
        catalogue,
        brought,
      });
    })();
    return () => {
      gone = true;
    };
  }, [credentials, numbers, keys, providers]);

  return accounts;
}

export function Agents(): ReactNode {
  const { held, agents, live, lines, connection, agentsError, agentsLoaded, insights } = useOrg();
  const me = meIn(useWhoami());
  const scopes = useScopes();
  const accounts = useAccounts();
  const [corners, setCorners] = useState<Corners>("everything");
  const ofToday = startedOn(lines, today().today);

  // Only shown when the gateway returns other members' corners (admins, operators).
  const theTeams = held.some((one) => somebodyElses(one, me));
  const rows: HeldAgent[] = theTeams ? through(held, corners, me) : agents;
  const routed = new Set((accounts.numbers ?? []).map((one) => one.route.agent));
  const known = new Set([...agents.map((one) => one.slug), ...routed]);
  const numbersOf = (slug: string): string[] =>
    (accounts.numbers ?? []).filter((one) => one.route.agent === slug && one.route.number !== null).map((one) => prettyNumber(one.route.number));
  const activeKeys = accounts.keys?.filter((key) => key.revoked_at === null) ?? [];
  const ready = accounts.catalogue?.providers.filter((one) => one.standing === READY) ?? [];
  const canIssue = WORLD === "production" && scopes !== null && scopes.includes("app");

  return (
    <Page>
      <PageHead
        title="Agents"
        lede="Which agents this gateway is holding right now — the list changes the moment a socket connects."
        actions={
          canIssue ? (
            <ButtonLink to="/tokens" size="base">
              New server token
            </ButtonLink>
          ) : undefined
        }
      />

      <Stats min={170}>
        <Stat label="Agents up" value={agents.length} of={`of ${known.size}`} />
        {accounts.numbers !== null ? (
          <Stat label="Numbers ringing" value={accounts.numbers.filter((one) => one.route.number !== null).length} of={accounts.free === null ? undefined : `· ${accounts.free} free`} />
        ) : (
          <Stat label="Calls live" value={live.length} />
        )}
        {accounts.keys !== null ? (
          <Stat label="Active tokens" value={activeKeys.length} of={`· ${accounts.keys.length - activeKeys.length} revoked`} />
        ) : (
          <Stat label="Calls today" value={ofToday.length} />
        )}
        {accounts.catalogue !== null && <Stat label="Providers ready" value={ready.length} of={`of ${accounts.catalogue.providers.length}`} />}
      </Stats>

      <Card>
        <CardHead
          title="Agents"
          meta="the list changes the moment a socket connects"
          action={
            <span className="agents-watching">
              <Dot tone={connection === "live" ? "green" : undefined} small />
              {connection === "live" ? "watching" : connection}
            </span>
          }
        >
          {theTeams && (
            <div className="agents-corners">
              <Chips options={CORNERS.map((one) => ({ value: one, label: one }))} value={corners} onChange={setCorners} />
            </div>
          )}
        </CardHead>
        <Refused>{agentsError}</Refused>
        {agentsLoaded && rows.length === 0 && (
          <Empty>
            {corners === "everything" ? (
              WORLD === "sandbox" ? (
                <>
                  Nothing of yours is running. <span className="ui-fixed">pinecall start</span> in a project puts its agents here.
                </>
              ) : (
                <>
                  Nothing is running in production: <span className="ui-fixed">pinecall start --prod</span> on your server holds it, on a server token.
                </>
              )
            ) : (
              <>Nothing here is {corners}.</>
            )}
          </Empty>
        )}
        {rows.length > 0 && <TableHead columns={COLUMNS} padding="9px 16px" labels={["Agent", "Doors", "Numbers", "Today>", "Score>"]} />}
        {rows.map((one, index) => {
          const onCalls = live.filter((line) => line.agent === one.slug).length;
          const last = lines.find((line) => line.agent === one.slug);
          const numbers = numbersOf(one.slug);
          return (
            <TableRow key={`${one.slug}/${one.holder?.holder ?? ""}`} columns={COLUMNS} padding="13px 16px" to={`/a/${one.slug}/overview`}>
              <div className="agents-name">
                <Avatar name={one.slug} letters={one.slug.slice(0, 1).toUpperCase()} tint={tintAt(index)} />
                <div style={{ minWidth: 0 }}>
                  <div className="ui-cell-strong ui-clip">{one.slug}</div>
                  {onCalls > 0 ? (
                    <div className="agents-live">
                      <Dot tone="green" small />
                      {onCalls === 1 ? "1 call live" : `${onCalls} calls live`}
                    </div>
                  ) : (
                    <div className="agents-idle">
                      {theTeams ? `${whoseCorner(one)} · ` : ""}idle{last === undefined ? "" : ` · last call ${ago(last.started_at)}`}
                    </div>
                  )}
                </div>
              </div>
              <div className="ui-tags">
                {one.channels.map((channel) => (
                  <Tag key={channel}>{channel}</Tag>
                ))}
              </div>
              <span className="agents-numbers ui-clip">{numbers.length === 0 ? "—" : numbers.join(", ")}</span>
              <span className="agents-figure">{insights?.agents.find((row) => row.slug === one.slug)?.calls ?? ofToday.filter((line) => line.agent === one.slug).length}</span>
              <Score share={insights?.agents.find((row) => row.slug === one.slug)?.score ?? null} />
            </TableRow>
          );
        })}
        {rows.length > 0 && (
          <CardFoot>
            <span>{rows.length > 1 ? "Every agent writes the same log — open one to read its turns." : "Open the agent to read its turns."}</span>
          </CardFoot>
        )}
      </Card>

      <Processes held={held} stops={scopes !== null && scopes.includes("app")} />

      {(accounts.keys !== null || accounts.catalogue !== null) && (
        <div className="agents-split">
          {accounts.keys !== null && <TokensInUse tokens={accounts.keys} />}
          {accounts.catalogue !== null && <ProvidersInUse catalogue={accounts.catalogue} brought={accounts.brought} />}
        </div>
      )}
    </Page>
  );
}

function TokensInUse({ tokens }: { tokens: Listed[] }): ReactNode {
  const shown = [...tokens].sort((a, b) => Number(a.revoked_at !== null) - Number(b.revoked_at !== null)).slice(0, 4);
  return (
    <Card>
      <CardHead title="API keys in use" action={<CardAction to="/tokens">Manage</CardAction>} />
      <div className="ui-card-list">
        {shown.length === 0 && <div className="agents-none">No token has been made yet.</div>}
        {shown.map((key) => (
          <Item
            key={key.fingerprint}
            name={key.label ?? key.fingerprint}
            sub={key.kind === "person" ? `${key.name ?? "a person"} · their own` : `the org's · ${key.env ?? ""}${key.created_by === null ? "" : ` · made by ${key.created_by}`}`}
            end={key.revoked_at === null ? <Pill tone="green">active</Pill> : <Pill tone="muted">revoked</Pill>}
          />
        ))}
      </div>
    </Card>
  );
}

function ProvidersInUse({ catalogue, brought }: { catalogue: Catalogue; brought: string[] }): ReactNode {
  const ready = catalogue.providers.filter((one) => one.standing === READY);
  // Order: the org's own vendors, then box defaults, then other ready vendors.
  const defaults = new Set(Object.values(catalogue.defaults).map((one) => one.split("/")[0] ?? one));
  const ranked = [...ready].sort(
    (a, b) =>
      Number(brought.includes(b.name)) - Number(brought.includes(a.name)) ||
      Number(defaults.has(b.name)) - Number(defaults.has(a.name)) ||
      a.name.localeCompare(b.name),
  );
  return (
    <Card>
      <CardHead
        title="Providers"
        meta={`${ready.length} ready · ${catalogue.providers.length - ready.length} need a key`}
        action={<CardAction to="/providers">Bring one</CardAction>}
      />
      <div className="ui-card-list">
        {ranked.slice(0, 4).map((one) => (
          <Item
            key={one.name}
            name={one.name.charAt(0).toUpperCase() + one.name.slice(1)}
            sub={providerLine(one, catalogue)}
            end={brought.includes(one.name) ? <Pill tone="green">ready</Pill> : <Pill tone="amber">box key</Pill>}
          />
        ))}
      </div>
    </Card>
  );
}

/** Today's judge pass rate as a coloured percent. */
function Score({ share }: { share: number | null }): ReactNode {
  if (share === null) return <span className="agents-figure agents-score">—</span>;
  const tone = share >= 0.9 ? "agents-score-good" : share >= 0.7 ? "agents-score-fair" : "agents-score-poor";
  return <span className={`agents-figure ${tone}`}>{Math.round(share * 100)}%</span>;
}

const JOB: Record<string, string> = { llm: "decides", stt: "hears", tts: "speaks" };

/** Vendor subtitle: the jobs it is default for, else its description. */
function providerLine(one: Catalogue["providers"][number], catalogue: Catalogue): string {
  const defaultFor = one.does.filter((job) => (catalogue.defaults[job] ?? "").split("/")[0] === one.name);
  if (defaultFor.length > 0) return `${defaultFor.map((job) => JOB[job]).join(", ")} · the default`;
  return `${one.does.map((job) => JOB[job]).join(", ")} · ${one.note}`;
}
