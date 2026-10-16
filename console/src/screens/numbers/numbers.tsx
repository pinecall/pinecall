/** Numbers screen: each number and whether a call to it rings the agent now, the org's accounts, calling out. */

import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { inTheWorld } from "../../lib/mode";
import { useOrg } from "../../lib/org";
import { useWorld } from "../../lib/world";
import { Button, Card, CardHead, Dot, Empty, Page, PageHead, Pill, Refused, Select, SelectItem, Tabs } from "../../ui";
import { Accounts } from "./accounts";
import { AddNumber } from "./add-number";
import {
  bringCarrier,
  dropCarrier,
  moveNumber,
  provisionOutbound,
  readAvailable,
  readCarriers,
  readCatalog,
  readNumbers,
  readOutbound,
  releaseNumber,
  type Answering,
  type Available,
  type Carrier,
  type Catalog,
  type Outbound,
} from "./door";
import { OutboundPanel } from "./outbound";
import { Path } from "./path";
import { ORIGIN_SAID, RINGS_SAID, comesThrough, countRings } from "./ways";
import "./numbers.css";

type Tab = "numbers" | "accounts" | "outbound";

const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "numbers", name: "Numbers" },
  { tab: "accounts", name: "Accounts" },
  { tab: "outbound", name: "Calling out" },
];

/** The tab is kept in `?tab=`, the page that adds a number at `?add=` with its way. Phone testing for developers is phone.tsx. */
export function Numbers(): ReactNode {
  const credentials = useCredentials();
  const { agents } = useOrg();
  const { world } = useWorld();
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some((one) => one.tab === params.get("tab")) ? (params.get("tab") as Tab) : "numbers";
  const adding = params.has("add");
  const [carriers, setCarriers] = useState<Carrier[] | undefined>(undefined);
  const [doors, setDoors] = useState<Answering[] | null>(null);
  const [available, setAvailable] = useState<Available | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [outbound, setOutbound] = useState<Outbound | null>(null);
  // Calls go out through one account: the first that places calls, unless another is picked.
  const [via, setVia] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    const [brought, answering, offered] = await Promise.all([readCarriers(credentials), readNumbers(credentials), readCatalog(credentials).catch(() => null)]);
    setCarriers(brought);
    setDoors(answering);
    setCatalog(offered);
    setAvailable(brought.length === 0 ? null : await readAvailable(credentials).catch(() => null));
    const dialling = brought.filter((one) => one.kind !== "whatsapp");
    const through = dialling.find((one) => one.account === via) ?? dialling[0];
    setVia(through?.account ?? null);
    setOutbound(through === undefined ? null : await readOutbound(credentials, dialling.length > 1 ? through.account : undefined).catch(() => null));
  }, [credentials, via]);

  useEffect(() => {
    let gone = false;
    reread().catch((failed: unknown) => {
      if (!gone) setRefused(saidBy(failed));
    });
    return () => {
      gone = true;
    };
  }, [reread]);

  // One request at a time: its refusal shown inline, the screen read again after.
  const move = async <T,>(work: () => Promise<T>): Promise<T> => {
    setBusy(true);
    setRefused(null);
    try {
      const answered = await work();
      await reread();
      return answered;
    } catch (failed) {
      setRefused(saidBy(failed));
      throw failed;
    } finally {
      setBusy(false);
    }
  };

  const pick = (changes: Record<string, string | null>): void => {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      if (value === null) next.delete(name);
      else next.set(name, value);
    }
    setParams(next);
  };

  // Adding a number is a page of its own, at `?add=` (and `?add=<way>` once one is chosen): the list
  // gives the screen to it, and its way back is the list again.
  if (adding && catalog !== null && carriers !== undefined) {
    return (
      <Page width={900}>
        <AddNumber
          catalog={catalog}
          world={world}
          way={params.get("add") || null}
          onWay={(way) => pick({ add: way ?? "" })}
          onClose={() => pick({ add: null })}
          carriers={carriers}
          agents={agents}
          available={available}
          busy={busy}
          move={move}
          onAdded={(number) => {
            setAdded(number);
            setOpen(number);
            pick({ add: null });
          }}
        />
        <Refused>{refused}</Refused>
      </Page>
    );
  }

  const rows = doors ?? [];
  const counted = countRings(rows);
  const dialling = (carriers ?? []).filter((one) => one.kind !== "whatsapp");

  return (
    <Page width={900}>
      <PageHead
        title="Phone numbers"
        lede="The numbers people call or write to, and which agent picks up."
        actions={
          <Button kind="primary" onClick={() => pick({ add: "", tab: null })} disabled={catalog === null}>
            Add a number
          </Button>
        }
      />
      <Tabs
        label="Phone numbers"
        tabs={TABS.map((one) => (one.tab === "numbers" && counted.waiting + counted.broken > 0 ? { ...one, mark: <Dot tone="amber" small /> } : one))}
        on={tab}
        onPick={(picked) => pick({ tab: picked === "numbers" ? null : picked })}
      />
      <Refused>{refused}</Refused>

      {tab === "numbers" && doors !== null && carriers !== undefined && (
        <Card>
          <CardHead title={`Numbers in ${world}`} meta={`${rows.length} · ${counted.ok} ring the agent${counted.waiting > 0 ? ` · ${counted.waiting} not reaching us yet` : ""}${counted.broken > 0 ? ` · ${counted.broken} not answered` : ""}`} />
          {rows.length === 0 ? (
            <Empty>No number rings or writes to an agent in {world} yet.</Empty>
          ) : (
            <>
              <div className="num-table-head">
                <span>Number</span>
                <span>Agent</span>
                <span>Comes through</span>
                <span>If it rings now</span>
              </div>
              {rows.map((row) => {
                const number = row.route.number ?? "";
                const through = comesThrough(row, carriers, catalog);
                const rings = RINGS_SAID[row.rings];
                const origin = ORIGIN_SAID[row.origin];
                const isOpen = open === number;
                return (
                  <Fragment key={`${row.route.channel}:${number}`}>
                    <button type="button" className="num-table-row" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : number)}>
                      <span className="num-cell-number">
                        {prettyNumber(number)}
                        {row.route.channel === "whatsapp" && <span className="num-cell-sub">WhatsApp</span>}
                      </span>
                      <span className="num-cell-agent" title={row.route.agent}>
                        → {row.route.agent}
                      </span>
                      <span className="num-cell-through" title={through.sub === "" ? through.name : `${through.name} · ${through.sub}`}>
                        {through.name}
                        <span className="num-cell-sub">{through.sub}</span>
                      </span>
                      <span className="num-cell-pills">
                        <Pill tone={rings.tone} small>
                          {rings.text}
                        </Pill>
                        <Pill tone={origin.tone} small>
                          {origin.text}
                        </Pill>
                      </span>
                      <span className="num-caret" aria-hidden>
                        ›
                      </span>
                    </button>
                    {isOpen && (
                      <Path
                        row={row}
                        busy={busy}
                        onMove={() => void move(() => moveNumber(credentials, number, row.route.env === "production" ? "sandbox" : "production")).catch(() => undefined)}
                        onRemove={() => void move(() => releaseNumber(credentials, number)).then(() => setOpen(null), () => undefined)}
                      />
                    )}
                  </Fragment>
                );
              })}
            </>
          )}
          {added !== null && <div className="num-added">Done. {prettyNumber(added)} is added; open it to see what a call to it goes through.</div>}
          <div className="num-foot">
            Every agent is on the web with nothing to turn on: this page is the telephone and WhatsApp. Move a number to another agent by adding it again; it moves on the next call, with
            nothing deployed. To reach your sandbox copy from your own phone, on the same numbers, open <a href={inTheWorld("sandbox", "/phone")}>Phone testing</a> in the sandbox.
          </div>
        </Card>
      )}

      {tab === "accounts" && carriers !== undefined && (
        <Accounts
          carriers={carriers}
          routed={doors ?? []}
          outbound={outbound}
          busy={busy}
          onDrop={(account) => move(() => dropCarrier(credentials, account)).catch(() => undefined)}
          onBring={(wanted) => move(() => bringCarrier(credentials, wanted)).then(() => undefined, () => undefined)}
        />
      )}

      {tab === "outbound" && carriers !== undefined && (
        <>
          {dialling.length > 1 && (
            <div className="num-fields num-fields-3">
              <div>
                <Select value={via ?? ""} onValueChange={(value) => setVia(value)}>
                  {dialling.map((one) => (
                    <SelectItem key={one.account} value={one.account}>
                      {one.label === "" ? one.account : `${one.label} · ${one.account}`}
                    </SelectItem>
                  ))}
                </Select>
              </div>
            </div>
          )}
          <OutboundPanel outbound={outbound} agents={agents} busy={busy} onProvision={(dryRun) => move(() => provisionOutbound(credentials, dryRun, dialling.length > 1 ? (via ?? undefined) : undefined))} />
        </>
      )}

    </Page>
  );
}

function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : String(failed);
}
