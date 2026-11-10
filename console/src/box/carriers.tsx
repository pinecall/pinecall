/** Carriers, the operator's: the addresses waiting for an answer first, then the carriers admitted, what the firewall should let in, the account numbers are bought on, and the test line. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { Copy, useMove } from "../numbers/parts";
import { CarrierPanel, NumbersAccountSection, TestLineSection } from "./carriers-panels";
import { admitCarrier, answerAsk, readAsks, readCarriers, type Ask, type CatalogCarrier } from "./telephony-door";
import { Head, OperatorPage, OrgLink, useDoor } from "./telephony-parts";

const EXPORT = "pinecall-runtime fence export > infra/terraform/environments/<env>/sip_sources.auto.tfvars.json";
const APPLY = "make tf-plan && make tf-apply";

const many = (count: number, one: string, more: string): string => `${count} ${count === 1 ? one : more}`;

function standingOf(carrier: CatalogCarrier): { mood: "held" | "none"; said: string } {
  if (carrier.fixed) return { mood: "held", said: "Always on" };
  return carrier.admitted ? { mood: "held", said: "Admitted" } : { mood: "none", said: "Not admitted" };
}

function Board(): ReactNode {
  const credentials = useCredentials();
  const catalog = useDoor(useCallback(() => readCarriers(credentials), [credentials]));
  const asks = useDoor(useCallback(() => readAsks(credentials), [credentials]));
  const mover = useMove();
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);

  const reread = (): void => (catalog.reread(), asks.reread());
  const answer = (ask: Ask, how: "approve" | "refuse"): void => void mover.move(() => answerAsk(credentials, ask.id, how)).then(reread, () => undefined);
  const admit = (carrier: CatalogCarrier, admitted: boolean): void => void mover.move(() => admitCarrier(credentials, carrier.kind, admitted)).then(reread, () => undefined);

  const waiting = (asks.value ?? []).filter((ask) => ask.state === "waiting");
  const answered = (asks.value ?? []).filter((ask) => ask.state !== "waiting");
  const carriers = catalog.value?.carriers ?? [];
  const fence = catalog.value?.fence;
  const opened = carriers.find((one) => one.kind === open);
  const refused = catalog.refused ?? asks.refused ?? mover.refused;

  return (
    <>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      <section className="tst-list" aria-label="Waiting for your answer">
        <Head icon="bell" title="Waiting for your answer" about="Addresses an organization asked to be let in from: its own phone system, or the carrier of a number it pointed here. Calls from one are turned away until you approve it.">
          {waiting.length > 0 && <span className="tst-head-stands">{waiting.length} waiting</span>}
        </Head>
        {asks.value === null && asks.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {waiting.map((ask) => (
          <div key={ask.id} className="tst-row tel-row">
            <span className="tst-row-words">
              <span className="tst-row-name">
                <code className="tel-mono">{ask.network}</code>
                <span className="tst-tag">{ask.source}</span>
              </span>
              <span className="tst-row-under">
                Asked by <OrgLink slug={ask.org} />, {ago(ask.asked_at)}. Approving lets calls from this address reach {ask.org}'s numbers, and nobody else's.
              </span>
            </span>
            <span className="tst-status tst-status-waiting tel-status">Waiting</span>
            <ConfirmButton label="Approve" asks="Let its calls in?" onConfirm={() => answer(ask, "approve")} />
            <ConfirmButton label="Refuse" asks="Turn it away?" danger onConfirm={() => answer(ask, "refuse")} />
          </div>
        ))}
        {asks.value !== null && waiting.length === 0 && <p className="dash-quiet tst-none">Nothing waits for you.</p>}
      </section>

      <section className="tst-list" aria-label="Carriers">
        <Head icon="numbers" title="Carriers" about="The phone companies this deployment takes calls from. An organization can only bring a number from one that is admitted.">
          {carriers.length > 0 && <span className="tst-head-stands">{carriers.filter((one) => one.admitted).length} of {carriers.length} admitted</span>}
        </Head>
        {catalog.value === null && catalog.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {carriers.map((carrier) => {
          const standing = standingOf(carrier);
          return (
            <div key={carrier.kind} className={open === carrier.kind ? "tst-row tst-row-on tel-row" : "tst-row tel-row"}>
              <button type="button" className="tst-row-main" onClick={() => setOpen(carrier.kind)}>
                <span className="tst-row-words">
                  <span className="tst-row-name">
                    <span className="dash-clip">{carrier.name}</span>
                    <span className="tst-tag">{carrier.control ? "Numbers listed and pointed for the org" : "The org pastes one address in its portal"}</span>
                  </span>
                  <span className="tst-row-under dash-clip">{carrier.numbers === 0 ? "No number comes through it" : `${many(carrier.numbers, "number comes", "numbers come")} through it`}</span>
                </span>
                <span className={`tst-status tst-status-${standing.mood} tel-status`}>{standing.said}</span>
              </button>
              {!carrier.fixed && !carrier.admitted && <ConfirmButton label="Admit" asks="Offer it to every org?" onConfirm={() => admit(carrier, true)} />}
              {!carrier.fixed && carrier.admitted && <ConfirmButton label="Stop admitting" asks={carrier.numbers === 0 ? "Stop offering it?" : `Cut off ${many(carrier.numbers, "number", "numbers")}?`} danger onConfirm={() => admit(carrier, false)} />}
            </div>
          );
        })}
        <p className="dash-quiet tel-note">Admitting a carrier offers it to every organization under Add a number, and lets calls in from its networks. Stopping does the opposite: its calls are turned away.</p>
      </section>

      {answered.length > 0 && (
        <section className="tst-list" aria-label="Addresses already answered">
          <Head icon="check" title="Addresses already answered" about="What you approved or refused before. Either answer can be turned around." />
          {answered.map((ask) => (
            <div key={ask.id} className="tst-row tel-row">
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <code className="tel-mono">{ask.network}</code>
                  <span className="tst-tag">{ask.source}</span>
                </span>
                <span className="tst-row-under">
                  For <OrgLink slug={ask.org} />, {ask.state} {ago(ask.decided_at ?? ask.asked_at)}
                  {ask.decided_by == null ? "" : ` by ${ask.decided_by}`}
                </span>
              </span>
              <span className={`tst-status tst-status-${ask.state === "approved" ? "held" : "broke"} tel-status`}>{ask.state === "approved" ? "Let in" : "Turned away"}</span>
              {ask.state === "approved" ? <ConfirmButton label="Revoke" asks="Turn its calls away?" danger onConfirm={() => answer(ask, "refuse")} /> : <ConfirmButton label="Approve" asks="Let its calls in?" onConfirm={() => answer(ask, "approve")} />}
            </div>
          ))}
        </section>
      )}

      {fence !== undefined && (
        <section className="tst-list" aria-label="What the firewall should let in">
          <Head icon="privacy" title="What the firewall should let in" about="Phone calls arrive on port 5060. It opens to the admitted carriers and to the addresses approved above, and to nobody else.">
            <span className="tst-head-stands">{many(fence.networks.length, "network", "networks")}</span>
          </Head>
          {carriers
            .filter((one) => one.admitted)
            .map((carrier) => (
              <div key={carrier.kind} className="tst-row tel-row">
                <span className="tst-row-words">
                  <span className="tst-row-name">{carrier.name}</span>
                  <span className="tst-row-under">Its published networks, read {carrier.read_on}</span>
                </span>
                <span className="tst-row-when">{many(carrier.networks.length, "network", "networks")}</span>
              </div>
            ))}
          {fence.openings.map((opening) => (
            <div key={`${opening.network} ${opening.reason}`} className="tst-row tel-row">
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <code className="tel-mono">{opening.network}</code>
                </span>
                <span className="tst-row-under">Approved for {opening.reason}</span>
              </span>
              <span className="tst-row-when">1 address</span>
            </div>
          ))}
          <div className="tel-apply">
            <span className="tel-apply-title">On a cluster, the cloud firewall follows this list only once you apply it.</span>
            <span className="dash-quiet">Until then an address you just approved is still closed, and one you revoked is still open. Write the list, then apply it:</span>
            <Copy text={EXPORT} />
            <Copy text={APPLY} />
          </div>
        </section>
      )}

      <NumbersAccountSection />
      <TestLineSection />
      {opened !== undefined && <CarrierPanel key={opened.kind} carrier={opened} onClose={close} />}
    </>
  );
}

export function CarriersPage(): ReactNode {
  return (
    <OperatorPage>
      <Board />
    </OperatorPage>
  );
}
