/** The second step of Add a number, one form per way: Twilio, a guided carrier, an own PBX, buying, WhatsApp. */

import { useState, type FormEvent, type ReactNode } from "react";

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { useLimits } from "../../lib/limits";
import { theBoxsOwnName } from "../../lib/mode";
import { Button, Dot, Input, Label, Select, SelectItem } from "../../ui";
import { AccountForm, mintedPassword } from "./accounts";
import { AgentPick, Copy, FirstCall, Planned, Setup } from "./add-parts";
import {
  bringCarrier,
  buyNumber,
  importNumber,
  type Available,
  type Carrier,
  type WantedNumber,
  type Wired,
} from "./door";
import type { Way } from "./ways";

/** What every form is told: the org's accounts and agents, what its accounts own, and how to run a move. */
export interface WayProps {
  carriers: Carrier[];
  agents: HeldAgent[];
  available: Available | null;
  busy: boolean;
  /** Runs one request at a time, shows its refusal, and reads the screen again after. */
  move: <T>(work: () => Promise<T>) => Promise<T>;
  onAdded: (number: string) => void;
}

/** The box's name as a carrier dials it: the host of the page's own origin, production's. */
export function boxHost(): string {
  return new URL(theBoxsOwnName()).hostname;
}

/** Twilio: connect the account once, pick a number it owns, read what will happen, connect. */
export function TwilioWay({ carriers, agents, available, busy, move, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const twilios = carriers.filter((one) => one.kind === "twilio");
  const [account, setAccount] = useState(twilios[0]?.account ?? "");
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  const [plan, setPlan] = useState<Wired | null>(null);
  const [another, setAnother] = useState(false);
  const chosen = twilios.find((one) => one.account === account)?.account ?? twilios[0]?.account ?? "";
  const owned = (available?.numbers ?? []).filter((one) => one.account === chosen);

  if (twilios.length === 0 || another) {
    return (
      <>
        <AccountForm kind="twilio" busy={busy} onBring={(wanted) => move(() => bringCarrier(credentials, wanted)).then(() => { setAccount(wanted.kind === "twilio" ? wanted.account_sid : ""); setAnother(false); })} />
        {another && (
          <div className="num-actions-flush">
            <Button size="xs" onClick={() => setAnother(false)} disabled={busy}>Back to my accounts</Button>
          </div>
        )}
      </>
    );
  }
  const wanted: WantedNumber = { number, agent, channel: "phone", account: chosen };
  const review = (event: FormEvent): void => {
    event.preventDefault();
    void move(() => importNumber(credentials, wanted, true)).then(setPlan, () => undefined);
  };
  return (
    <form className="num-way" onSubmit={review}>
      <div>
        <Label>Twilio account</Label>
        <div className="num-account-pick">
          <Select value={chosen} onValueChange={(value) => { setAccount(value); setPlan(null); }}>
            {twilios.map((one) => (
              <SelectItem key={one.account} value={one.account}>{one.label === "" ? one.account : `${one.label} · ${one.account}`}</SelectItem>
            ))}
          </Select>
          <Button size="xs" onClick={() => setAnother(true)} disabled={busy}>Connect another</Button>
        </div>
      </div>
      <div>
        <div className="num-q">Which number?</div>
        <div className="num-q-sub">Every number on the account, read from Twilio just now.</div>
      </div>
      <div className="num-list" role="radiogroup">
        {owned.length === 0 && <div className="num-list-empty">This account owns no number Twilio lists.</div>}
        {owned.map((one) => (
          <label key={one.number} className="num-list-row">
            <input type="radio" name="twilio-number" value={one.number} disabled={one.imported} checked={number === one.number} onChange={() => { setNumber(one.number); setPlan(null); }} />
            <span className="num-list-number">{prettyNumber(one.number)}</span>
            <span className="num-list-name">{one.name === one.number ? "" : one.name}</span>
            {one.imported && <span className="num-list-note">already here</span>}
          </label>
        ))}
      </div>
      <AgentPick agents={agents} agent={agent} onAgent={(value) => { setAgent(value); setPlan(null); }} />
      {plan === null ? (
        <div className="num-actions-flush">
          <Button kind="primary" type="submit" disabled={busy || number === "" || agent === ""}>{busy ? "Checking…" : "Review"}</Button>
        </div>
      ) : (
        <Planned plan={plan} busy={busy} confirm="Connect number" onConfirm={() => void move(() => importNumber(credentials, wanted, false)).then(() => onAdded(number), () => undefined)} onCancel={() => setPlan(null)} />
      )}
    </form>
  );
}

/** A carrier of the catalog: the number stays there, its portal sends it here, and the first call turns it green. */
export function GuidedWay({ way, agents, busy, move, onAdded }: WayProps & { way: Way }): ReactNode {
  const credentials = useCredentials();
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  const [added, setAdded] = useState<string | null>(null);
  const e164 = number.replace(/[\s()-]/g, "");

  const add = (event: FormEvent): void => {
    event.preventDefault();
    void move(() => importNumber(credentials, { number: e164, agent, channel: "phone", hooked: true, ...(way.via === undefined ? {} : { via: way.via }) }, false)).then(() => setAdded(e164), () => undefined);
  };
  return (
    <form className="num-way" onSubmit={add}>
      <div className="num-fields num-fields-flush">
        <div>
          <Label>Your {way.name} number</Label>
          <Input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="+34 910 555 019" required autoComplete="off" disabled={added !== null} />
        </div>
      </div>
      <AgentPick agents={agents} agent={agent} onAgent={setAgent} />
      <Setup title={`In ${way.name}'s portal`} meta="a SIP connection pointing here, then the number on it">
        <dt>Send calls to</dt>
        <dd><Copy text={`sip:${e164 === "" ? "+…" : e164}@${boxHost()}`} /></dd>
        <dt>Port and transport</dt>
        <dd className="num-mono">5060 · UDP</dd>
        <dt>Number format</dt>
        <dd>E.164, with the +</dd>
        <dt>Authentication</dt>
        <dd>By IP. This box already accepts {way.name}'s networks.</dd>
      </Setup>
      {added === null ? (
        <div className="num-actions-flush">
          <Button kind="primary" type="submit" disabled={busy || e164 === "" || agent === ""}>{busy ? "Adding…" : "Add number"}</Button>
        </div>
      ) : (
        <FirstCall number={added} onReached={() => onAdded(added)} />
      )}
    </form>
  );
}

/** An own PBX: the box mints its pair, the operator approves its addresses once, and the PBX is set up meanwhile. */
export function PbxWay({ carriers, agents, busy, move, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const peers = carriers.filter((one) => one.kind === "sip");
  const [peer, setPeer] = useState(peers[0]?.account ?? "");
  const [label, setLabel] = useState("");
  const [addresses, setAddresses] = useState("");
  const [outbound, setOutbound] = useState("");
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  const [password] = useState(mintedPassword);
  const [done, setDone] = useState<{ username: string; password: string | null } | null>(null);
  const isNew = peers.length === 0 || peer === "";
  const username = isNew ? usernameOf(label) || "pbx" : peer;

  const add = (event: FormEvent): void => {
    event.preventDefault();
    const e164 = number.replace(/[\s()-]/g, "");
    const brought = isNew
      ? () =>
          bringCarrier(credentials, {
            kind: "sip",
            username,
            password,
            addresses: addresses.split(/[\s,]+/).filter(Boolean),
            ...(label.trim() === "" ? {} : { label: label.trim() }),
            ...(outbound.trim() === "" ? {} : { outbound_host: outbound.trim() }),
          })
      : async () => undefined;
    void move(async () => {
      await brought();
      return importNumber(credentials, { number: e164, agent, channel: "phone", account: username }, false);
    }).then(() => setDone({ username, password: isNew ? password : null }), () => undefined);
  };

  if (done !== null) {
    return (
      <div className="num-way">
        <Setup title="In your PBX" meta="a SIP trunk to Pinecall">
          <dt>Host</dt>
          <dd><Copy text={boxHost()} /></dd>
          <dt>Port and transport</dt>
          <dd className="num-mono">5060 · UDP or TCP</dd>
          <dt>Username</dt>
          <dd><Copy text={done.username} /></dd>
          {done.password !== null && (
            <>
              <dt>Password · shown once</dt>
              <dd><Copy text={done.password} /></dd>
            </>
          )}
          <dt>Codecs</dt>
          <dd>G.722, G.711 µ-law, G.711 A-law</dd>
        </Setup>
        <div className="num-waiting">
          <Dot tone="amber" />
          <span>
            <span className="num-waiting-title">The box operator approves your addresses once</span>
            <span className="num-waiting-say">Set the PBX up now; calls reach the agent as soon as they are approved. Every other number from this PBX is admitted right away.</span>
          </span>
        </div>
        <div className="num-actions-flush">
          <Button kind="primary" onClick={() => onAdded(number)}>Done</Button>
        </div>
      </div>
    );
  }
  return (
    <form className="num-way" onSubmit={add}>
      {peers.length > 0 && (
        <div>
          <Label>PBX</Label>
          <Select value={peer} onValueChange={setPeer}>
            {peers.map((one) => (
              <SelectItem key={one.account} value={one.account}>{one.label === "" ? one.account : one.label}</SelectItem>
            ))}
            <SelectItem value="">+ Another PBX</SelectItem>
          </Select>
        </div>
      )}
      <div className="num-fields num-fields-flush">
        {isNew && (
          <>
            <div>
              <Label>Name</Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="FreePBX · Oficina Madrid" required autoComplete="off" />
            </div>
            <div>
              <Label>It calls from · an IP, or a /24 at most</Label>
              <Input value={addresses} onChange={(e) => setAddresses(e.target.value)} placeholder="198.51.100.10" required autoComplete="off" />
            </div>
            <div>
              <Label>Calls go out through · optional</Label>
              <Input value={outbound} onChange={(e) => setOutbound(e.target.value)} placeholder="pbx.example.com" autoComplete="off" />
            </div>
          </>
        )}
        <div>
          <Label>Number it sends</Label>
          <Input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="+34 910 123 456" required autoComplete="off" />
        </div>
      </div>
      <AgentPick agents={agents} agent={agent} onAgent={setAgent} />
      <div className="num-actions-flush">
        <Button kind="primary" type="submit" disabled={busy || agent === ""}>{busy ? "Sending…" : isNew ? "Ask for approval" : "Add number"}</Button>
        <span className="num-note">The box makes the PBX's username and password; you type them into the PBX.</span>
      </div>
    </form>
  );
}

/** Buying: the box finds a number, says which, and buys it on a second click. */
export function BuyWay({ agents, busy, move, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const stock = useLimits()?.numbers ?? null;
  const [country, setCountry] = useState("US");
  const [areaCode, setAreaCode] = useState("");
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  const [plan, setPlan] = useState<Wired | null>(null);
  const wanted = { country: country.trim().toUpperCase(), ...(areaCode.trim() === "" ? {} : { area_code: areaCode.trim() }), agent, channel: "phone" as const };
  const review = (event: FormEvent): void => {
    event.preventDefault();
    void move(() => buyNumber(credentials, wanted, true)).then(setPlan, () => undefined);
  };
  return (
    <form className="num-way" onSubmit={review}>
      <div className="num-fields num-fields-flush">
        <div>
          <Label>Country · two letters</Label>
          <Input value={country} onChange={(e) => { setCountry(e.target.value); setPlan(null); }} maxLength={2} required autoComplete="off" />
        </div>
        <div>
          <Label>Area code · optional</Label>
          <Input value={areaCode} onChange={(e) => { setAreaCode(e.target.value); setPlan(null); }} placeholder="415" autoComplete="off" />
        </div>
      </div>
      <AgentPick agents={agents} agent={agent} onAgent={(value) => { setAgent(value); setPlan(null); }} />
      {plan === null ? (
        <div className="num-actions-flush">
          <Button kind="primary" type="submit" disabled={busy || agent === ""}>{busy ? "Looking…" : "Find a number"}</Button>
          <span className="num-note">
            Nothing is bought until you confirm the number found.
            {stock !== null && ` Bought numbers here: ${Math.round(stock.used)}${stock.limit === null ? ", no limit" : ` of ${stock.limit}`}.`}
          </span>
        </div>
      ) : (
        <Planned plan={plan} busy={busy} confirm={`Buy ${prettyNumber(plan.route.number ?? "")} and connect`} onConfirm={() => void move(() => buyNumber(credentials, wanted, false)).then((wired) => onAdded(wired.route.number ?? ""), () => undefined)} onCancel={() => setPlan(null)} />
      )}
    </form>
  );
}

/** WhatsApp: connect the number at Meta once, then route it to an agent. */
export function WhatsAppWay({ carriers, agents, available, busy, move, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const metas = carriers.filter((one) => one.kind === "whatsapp");
  const owned = (available?.numbers ?? []).filter((one) => metas.some((meta) => meta.account === one.account) && !one.imported);
  const [number, setNumber] = useState(owned[0]?.number ?? "");
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  if (metas.length === 0) {
    return <AccountForm kind="whatsapp" busy={busy} onBring={(wanted) => move(() => bringCarrier(credentials, wanted))} />;
  }
  const account = owned.find((one) => one.number === number)?.account;
  const add = (event: FormEvent): void => {
    event.preventDefault();
    void move(() => importNumber(credentials, { number, agent, channel: "whatsapp", ...(account === undefined ? {} : { account }) }, false)).then(() => onAdded(number), () => undefined);
  };
  return (
    <form className="num-way" onSubmit={add}>
      <div>
        <Label>WhatsApp number</Label>
        <Select value={number} onValueChange={setNumber}>
          {owned.map((one) => (
            <SelectItem key={one.number} value={one.number}>{`${one.name} · ${prettyNumber(one.number)}`}</SelectItem>
          ))}
        </Select>
      </div>
      <AgentPick agents={agents} agent={agent} onAgent={setAgent} />
      <div className="num-actions-flush">
        <Button kind="primary" type="submit" disabled={busy || number === "" || agent === ""}>{busy ? "Connecting…" : "Connect"}</Button>
      </div>
    </form>
  );
}

// The PBX's username: its name in letters and digits, which the PBX types; the gateway keys it.
function usernameOf(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32);
}
