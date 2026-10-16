/** Carriers: which carriers may send calls to this box, the addresses orgs asked for, and the fence as it stands. */

import { useCallback, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../../lib/format";
import { Button, Card, CardFoot, CardHead, Empty, Page, PageHead, Pill, Refused, Stat, Stats, Switch, TableHead, TableRow, TextAction } from "../../ui";
import { admitCarrier, decideNetwork, readBoxCarriers, readCarrierNetworks, type CarrierNetwork } from "./door-floor";
import { useDoor, useMove } from "./use-door";
import "./box.css";

const CARRIERS = "minmax(0,1fr) minmax(0,1.4fr) 110px 90px 52px";

const ASKS = "minmax(0,1.2fr) minmax(0,1fr) minmax(0,1.2fr) 190px";

const STATE_TONE = { waiting: "amber", approved: "green", refused: "red" } as const;

/**
 * The screen. Port 5060 opens to the carriers admitted here and to the addresses approved here,
 * and to nothing else: the cloud's firewall admits the list once Terraform applies it. A carrier off
 * is offered to no org; an address waiting fences no number until it is approved.
 */
export function BoxCarriers(): ReactNode {
  const credentials = useCredentials();
  const box = useDoor(useCallback(() => readBoxCarriers(credentials), [credentials]));
  const asks = useDoor(useCallback(() => readCarrierNetworks(credentials), [credentials]));
  const acting = useMove();

  const rereadBoth = async (): Promise<void> => {
    await Promise.all([box.reread(), asks.reread()]);
  };
  const waiting = (asks.value ?? []).filter((ask) => ask.state === "waiting");
  const decided = (asks.value ?? []).filter((ask) => ask.state !== "waiting");
  const fence = box.value?.fence;

  return (
    <Page width={1060} tight>
      <PageHead title="Carriers" lede="Which carriers may send calls to this box. Port 5060 opens to their networks and to the addresses you approve, and to nothing else." />
      <Refused>{box.refused ?? asks.refused ?? acting.refused}</Refused>

      {box.value !== undefined && fence !== undefined && (
        <Stats min={170}>
          <Stat label="5060 open beyond Twilio to" value={fence.openings.length} of="networks" />
          <Stat label="Carriers on" value={box.value.carriers.filter((one) => one.admitted).length} of={`of ${box.value.carriers.length}`} />
          <Stat label="Waiting for you" value={waiting.length} of={waiting.length === 1 ? "address" : "addresses"} />
        </Stats>
      )}

      <Card>
        <CardHead title="Addresses orgs asked for" meta="their own PBX, or a number hooked from networks of its own" />
        {asks.value !== undefined && asks.value.length === 0 && <Empty>No org has asked for an address.</Empty>}
        {asks.value !== undefined && asks.value.length > 0 && <TableHead columns={ASKS} labels={["Org", "Network", "Asked", ""]} />}
        {[...waiting, ...decided].map((ask) => (
          <Ask key={ask.id} ask={ask} busy={acting.busy} onDecide={(answer) => void acting.move(async () => { await decideNetwork(credentials, ask.id, answer); await rereadBoth(); })} />
        ))}
        <CardFoot>Refused before it reaches you: anything wider than a /24, and private ranges.</CardFoot>
      </Card>

      {box.value !== undefined && (
        <Card>
          <CardHead title="Carriers this box admits" meta="an org sees only these under Add a number" />
          <TableHead columns={CARRIERS} labels={["Carrier", "How an org connects", "Signalling", "Numbers", "On"]} />
          {box.value.carriers.map((carrier) => (
            <TableRow key={carrier.kind} columns={CARRIERS}>
              <span className="ui-cell-strong">{carrier.name}</span>
              <span className="ui-cell-ink">{carrier.control ? "API: lists, points, buys, calls out" : "SIP: the org pastes one address"}</span>
              <span className="ui-cell-ink" title={`${carrier.source}, read ${carrier.read_on}`}>
                {carrier.networks.length} networks
              </span>
              <span className="ui-cell-ink">{carrier.admitted ? carrier.numbers : "—"}</span>
              <span>
                {carrier.fixed ? (
                  <Pill tone="gray" small>always</Pill>
                ) : (
                  <Switch on={carrier.admitted} label={`Admit ${carrier.name}`} onChange={(on) => void acting.move(async () => { await admitCarrier(credentials, carrier.kind, on); await box.reread(); })} />
                )}
              </span>
            </TableRow>
          ))}
          <CardFoot>Twilio is the box's own carrier. Each list is read from the carrier's own page, with the day; hover a count for its source.</CardFoot>
        </Card>
      )}

      {fence !== undefined && (
        <Card>
          <CardHead title="The fence right now" meta={`${fence.networks.length} networks for the cloud's firewall, Twilio's with them`} />
          {fence.openings.length === 0 ? (
            <Empty>Twilio's networks alone: nothing else is admitted.</Empty>
          ) : (
            <div className="box-fence">
              {fence.openings.map((opening) => (
                <span key={`${opening.network}-${opening.reason}`} className="box-fence-line">
                  {opening.network} <span className="box-fence-why">{opening.reason}</span>
                </span>
              ))}
            </div>
          )}
          <CardFoot>The cloud's firewall admits what Terraform last applied: `pinecall-runtime fence export` into the environment's `sip_sources.auto.tfvars.json`, then `make tf-plan` and `make tf-apply`, bring it level with this list.</CardFoot>
        </Card>
      )}
    </Page>
  );
}

function Ask({ ask, busy, onDecide }: { ask: CarrierNetwork; busy: boolean; onDecide: (answer: "approve" | "refuse") => void }): ReactNode {
  return (
    <TableRow columns={ASKS}>
      <span className="ui-cell-strong ui-clip">
        {ask.org}
        <span className="box-sub">{ask.source}</span>
      </span>
      <span className="box-mono">{ask.network}</span>
      <span className="ui-cell-ink">{ask.state === "waiting" ? `asked ${ago(ask.asked_at)}` : `${ask.state} ${ago(ask.decided_at ?? ask.asked_at)}${ask.decided_by === null ? "" : ` by ${ask.decided_by}`}`}</span>
      <span className="box-line">
        {ask.state === "waiting" ? (
          <>
            <Button size="xs" kind="primary" disabled={busy} onClick={() => onDecide("approve")}>Approve</Button>
            <Button size="xs" disabled={busy} onClick={() => onDecide("refuse")}>Refuse</Button>
          </>
        ) : (
          <>
            <Pill tone={STATE_TONE[ask.state]} small>{ask.state}</Pill>
            <TextAction onClick={() => onDecide(ask.state === "approved" ? "refuse" : "approve")}>{ask.state === "approved" ? "Revoke" : "Approve"}</TextAction>
          </>
        )}
      </span>
    </TableRow>
  );
}
