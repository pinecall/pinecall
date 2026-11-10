/** One form per way to add a number: buying one, bringing one from Twilio, pointing one from a carrier, an own PBX, WhatsApp. */

import { useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { addNumber, bringCarrier, buyNumber, type Carrier, type Owned, type WantedCarrier, type WantedNumber, type Wired } from "./door";
import { AgentField, Copy, Plan, type Mover } from "./parts";
import { accountName, e164, shown, type Way } from "./words";

/** What every form is told. */
export interface WayProps {
  agents: readonly string[];
  /** The agent the form was opened for; none lets the person choose. */
  agent: string | undefined;
  carriers: readonly Carrier[];
  owned: readonly Owned[];
  mover: Mover;
  /** Where a carrier or a PBX sends this environment's calls; null when the gateway does not say. */
  sipDomain: string | null;
  /** An account was kept: the accounts and what they own are read again. */
  onAccount: () => Promise<void>;
  /** The number rings: what the person must still do outside, if anything, is said under it. */
  onAdded: (number: string, after?: ReactNode) => void;
}

function Submit({ busy, doing, children, disabled = false }: { busy: boolean; doing: string; children: ReactNode; disabled?: boolean }): ReactNode {
  return (
    <div className="cfg-dialog-foot">
      <button type="submit" className="cfg-save" disabled={busy || disabled}>
        {busy ? doing : children}
      </button>
    </div>
  );
}

const COUNTRIES = [
  { value: "US", label: "United States" },
  { value: "CA", label: "Canada" },
  { value: "GB", label: "United Kingdom" },
  { value: "ES", label: "Spain" },
  { value: "MX", label: "Mexico" },
  { value: "AR", label: "Argentina" },
  { value: "UY", label: "Uruguay" },
  { value: "CL", label: "Chile" },
  { value: "CO", label: "Colombia" },
  { value: "BR", label: "Brazil" },
  { value: "DE", label: "Germany" },
  { value: "FR", label: "France" },
  { value: "AU", label: "Australia" },
];

/** Buying: the platform finds a number, says which, and buys it on the second click. */
export function BuyWay({ agents, agent: fixed, mover, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const [country, setCountry] = useState("US");
  const [area, setArea] = useState("");
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const [plan, setPlan] = useState<Wired | null>(null);
  const wanted = { country, ...(area.trim() === "" ? {} : { area_code: area.trim() }), agent, channel: "phone" as const };
  const find = (event: FormEvent): void => {
    event.preventDefault();
    void mover.move(() => buyNumber(credentials, wanted, true)).then(setPlan, () => undefined);
  };
  if (plan !== null) {
    return <Plan plan={plan} busy={mover.busy} confirm={`Buy ${shown(plan.route.number)}`} onBack={() => setPlan(null)} onConfirm={() => void mover.move(() => buyNumber(credentials, wanted, false)).then((wired) => onAdded(wired.route.number ?? ""), () => undefined)} />;
  }
  return (
    <form className="num-form" onSubmit={find}>
      <Field label="Country">
        <Select label="Country" items={COUNTRIES} value={country} onChange={setCountry} />
      </Field>
      <Field label="Area code">
        <input className="cfg-input" aria-label="Area code" placeholder="Optional: 415" inputMode="numeric" value={area} onChange={(event) => setArea(event.target.value)} />
      </Field>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <span className="num-hint">Nothing is bought until you confirm the number found.</span>
      <Submit busy={mover.busy} doing="Looking…" disabled={agent === ""}>
        Find a number
      </Submit>
    </form>
  );
}

function AccountForm({ kind, mover, onBring }: { kind: "twilio" | "whatsapp"; mover: Mover; onBring: (wanted: WantedCarrier) => Promise<void> }): ReactNode {
  const [label, setLabel] = useState("");
  const [id, setId] = useState("");
  const [user, setUser] = useState("");
  const [secret, setSecret] = useState("");
  const bring = (event: FormEvent): void => {
    event.preventDefault();
    const called = label.trim() === "" ? {} : { label: label.trim() };
    void onBring(kind === "twilio" ? { kind, account_sid: id.trim(), user: user.trim() || id.trim(), secret, ...called } : { kind, phone_number_id: id.trim(), access_token: secret.trim(), ...called }).catch(() => undefined);
  };
  return (
    <form className="num-form" onSubmit={bring}>
      <p className="num-hint">{kind === "twilio" ? "Connect the account once. It is checked with Twilio, kept encrypted, and never shown again." : "Connect the number at Meta once. The agent's replies go out on this token."}</p>
      <Field label={kind === "twilio" ? "Account SID" : "Phone number ID"}>
        <input className="cfg-input" aria-label={kind === "twilio" ? "Account SID" : "Phone number ID"} placeholder={kind === "twilio" ? "AC…" : "From Meta's WhatsApp settings"} required spellCheck={false} autoComplete="off" value={id} onChange={(event) => setId(event.target.value)} />
      </Field>
      {kind === "twilio" && (
        <Field label="API key SID">
          <input className="cfg-input" aria-label="API key SID" placeholder="Optional: SK…, else the account's own" spellCheck={false} autoComplete="off" value={user} onChange={(event) => setUser(event.target.value)} />
        </Field>
      )}
      <Field label={kind === "twilio" ? "Secret" : "Access token"}>
        <input className="cfg-input" type="password" aria-label={kind === "twilio" ? "Secret" : "Access token"} placeholder={kind === "twilio" ? "The key's secret, or the auth token" : "A system user's, so it does not expire"} required autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} />
      </Field>
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="Optional" autoComplete="off" value={label} onChange={(event) => setLabel(event.target.value)} />
      </Field>
      <Submit busy={mover.busy} doing="Connecting…">
        {kind === "twilio" ? "Connect Twilio" : "Connect WhatsApp"}
      </Submit>
    </form>
  );
}

/** Twilio: the account connected once, a number it owns picked, what will happen read, then connected. */
export function TwilioWay({ agents, agent: fixed, carriers, owned, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const accounts = carriers.filter((one) => one.kind === "twilio");
  const [account, setAccount] = useState("");
  const [another, setAnother] = useState(false);
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const [plan, setPlan] = useState<Wired | null>(null);
  const chosen = accounts.find((one) => one.account === account)?.account ?? accounts[0]?.account ?? "";

  if (accounts.length === 0 || another) {
    return <AccountForm kind="twilio" mover={mover} onBring={async (wanted) => (await mover.move(() => bringCarrier(credentials, wanted)), await onAccount(), setAnother(false))} />;
  }
  const wanted: WantedNumber = { number, agent, channel: "phone", account: chosen };
  if (plan !== null) {
    return <Plan plan={plan} busy={mover.busy} confirm={`Connect ${shown(number)}`} onBack={() => setPlan(null)} onConfirm={() => void mover.move(() => addNumber(credentials, wanted, false)).then(() => onAdded(number), () => undefined)} />;
  }
  const theirs = owned.filter((one) => one.account === chosen);
  const review = (event: FormEvent): void => {
    event.preventDefault();
    void mover.move(() => addNumber(credentials, wanted, true)).then(setPlan, () => undefined);
  };
  return (
    <form className="num-form" onSubmit={review}>
      <Field label="Twilio account">
        <Select label="Twilio account" searchable={false} items={[...accounts.map((one) => ({ value: one.account, label: accountName(one), detail: one.account })), { value: "+", label: "Connect another account" }]} value={chosen} onChange={(picked) => (picked === "+" ? setAnother(true) : (setAccount(picked), setNumber("")))} />
      </Field>
      <Field label="Which number">
        <div className="num-owned" role="radiogroup" aria-label="Which number">
          {theirs.length === 0 && <p className="dash-quiet">This account owns no number Twilio lists.</p>}
          {theirs.map((one) => {
            const taken = one.imported || one.held_elsewhere;
            return (
              <label key={one.number} className={taken ? "num-owned-row num-owned-taken" : "num-owned-row"}>
                <input type="radio" name="owned" disabled={taken} checked={number === one.number} onChange={() => setNumber(one.number)} />
                <span className="num-owned-number">{shown(one.number)}</span>
                <span className="num-owned-name dash-clip">{one.imported ? "already here" : one.held_elsewhere ? "in use elsewhere" : one.name === one.number || one.name === shown(one.number).replace("+1 ", "") ? "" : one.name}</span>
              </label>
            );
          })}
        </div>
      </Field>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Checking…" disabled={number === "" || agent === ""}>
        Review
      </Submit>
    </form>
  );
}

/** A carrier of the catalog: the number stays there and its portal sends it here; the number's path says the address to paste. */
export function GuidedWay({ way, agents, agent: fixed, sipDomain, mover, onAdded }: WayProps & { way: Way }): ReactNode {
  const credentials = useCredentials();
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const add = (event: FormEvent): void => {
    event.preventDefault();
    const typed = e164(number);
    void mover.move(() => addNumber(credentials, { number: typed, agent, channel: "phone", hooked: true, ...(way.via === undefined ? {} : { via: way.via }) }, false)).then(
      () =>
        onAdded(
          typed,
          <>
            <dl className="num-setup">
              <dt>Send calls to</dt>
              <dd>{sipDomain === null ? "Pinecall's support gives you the address" : <Copy text={`sip:${typed}@${sipDomain}:5060`} />}</dd>
              <dt>Transport</dt>
              <dd>UDP, port 5060</dd>
              <dt>Number format</dt>
              <dd>E.164, with its +</dd>
            </dl>
            <p className="num-hint">Set this in the carrier's portal. The first step below turns green on the first call that arrives.</p>
          </>,
        ),
      () => undefined,
    );
  };
  return (
    <form className="num-form" onSubmit={add}>
      <Field label="Your number">
        <input className="cfg-input" aria-label="Your number" placeholder="+34 910 555 019" required autoComplete="off" value={number} onChange={(event) => setNumber(event.target.value)} />
        <span className="num-hint">With its country code. It stays with your carrier; only its calls come here.</span>
      </Field>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Adding…" disabled={agent === ""}>
        Add number
      </Submit>
    </form>
  );
}

// A password for a PBX's trunk: made here, shown once, typed into the PBX.
function mintedPassword(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return btoa(String.fromCharCode(...bytes)).replace(/[+/=]/g, "").slice(0, 24);
}

const usernameOf = (name: string): string => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32);

/** An own PBX: the trunk's username and password are made here, its addresses are approved once by the operator, and the PBX is set up meanwhile. */
export function PbxWay({ agents, agent: fixed, carriers, sipDomain, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const peers = carriers.filter((one) => one.kind === "sip");
  const [peer, setPeer] = useState(peers[0]?.account ?? "");
  const [label, setLabel] = useState("");
  const [addresses, setAddresses] = useState("");
  const [outbound, setOutbound] = useState("");
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const [password] = useState(mintedPassword);
  const fresh = peer === "";
  const username = fresh ? usernameOf(label) || "pbx" : peer;

  const add = (event: FormEvent): void => {
    event.preventDefault();
    const typed = e164(number);
    void mover
      .move(async () => {
        if (fresh) {
          await bringCarrier(credentials, { kind: "sip", username, password, addresses: addresses.split(/[\s,]+/).filter(Boolean), ...(label.trim() === "" ? {} : { label: label.trim() }), ...(outbound.trim() === "" ? {} : { outbound_host: outbound.trim() }) });
          await onAccount();
        }
        return addNumber(credentials, { number: typed, agent, channel: "phone", account: username }, false);
      })
      .then(
        () =>
          onAdded(
            typed,
            <dl className="num-setup">
              <dt>Host</dt>
              <dd>{sipDomain === null ? "Pinecall's support gives you the address" : <Copy text={sipDomain} />}</dd>
              <dt>Port</dt>
              <dd>5060, UDP or TCP</dd>
              <dt>Username</dt>
              <dd>
                <Copy text={username} />
              </dd>
              {fresh && (
                <>
                  <dt>Password, shown once</dt>
                  <dd>
                    <Copy text={password} />
                  </dd>
                </>
              )}
              <dt>Codecs</dt>
              <dd>G.722, G.711 µ-law, G.711 A-law</dd>
              <dt>Before it rings</dt>
              <dd>The operator approves your addresses once. Set the PBX up meanwhile.</dd>
            </dl>,
          ),
        () => undefined,
      );
  };
  return (
    <form className="num-form" onSubmit={add}>
      {peers.length > 0 && (
        <Field label="PBX">
          <Select label="PBX" searchable={false} items={[...peers.map((one) => ({ value: one.account, label: one.label === "" ? one.account : one.label })), { value: "", label: "Another PBX" }]} value={peer} onChange={setPeer} />
        </Field>
      )}
      {fresh && (
        <>
          <Field label="Name">
            <input className="cfg-input" aria-label="Name" placeholder="FreePBX, Madrid office" required autoComplete="off" value={label} onChange={(event) => setLabel(event.target.value)} />
          </Field>
          <Field label="It calls from">
            <input className="cfg-input" aria-label="It calls from" placeholder="198.51.100.10" required spellCheck={false} autoComplete="off" value={addresses} onChange={(event) => setAddresses(event.target.value)} />
            <span className="num-hint">Its public IP addresses, separated by commas; a /24 at most.</span>
          </Field>
          <Field label="Calls go out through">
            <input className="cfg-input" aria-label="Calls go out through" placeholder="Optional: pbx.example.com" spellCheck={false} autoComplete="off" value={outbound} onChange={(event) => setOutbound(event.target.value)} />
          </Field>
        </>
      )}
      <Field label="Number it sends">
        <input className="cfg-input" aria-label="Number it sends" placeholder="+34 910 123 456" required autoComplete="off" value={number} onChange={(event) => setNumber(event.target.value)} />
      </Field>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Sending…" disabled={agent === ""}>
        {fresh ? "Ask for approval" : "Add number"}
      </Submit>
    </form>
  );
}

/** WhatsApp: the number connected at Meta once, then sent to an agent. */
export function WhatsAppWay({ agents, agent: fixed, carriers, owned, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const metas = carriers.filter((one) => one.kind === "whatsapp");
  const theirs = owned.filter((one) => metas.some((meta) => meta.account === one.account) && !one.imported);
  const [picked, setPicked] = useState("");
  const [another, setAnother] = useState(false);
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const number = theirs.some((one) => one.number === picked) ? picked : (theirs[0]?.number ?? "");

  if (metas.length === 0 || another) {
    return <AccountForm kind="whatsapp" mover={mover} onBring={async (wanted) => (await mover.move(() => bringCarrier(credentials, wanted)), await onAccount(), setAnother(false))} />;
  }
  const add = (event: FormEvent): void => {
    event.preventDefault();
    const account = theirs.find((one) => one.number === number)?.account;
    void mover.move(() => addNumber(credentials, { number, agent, channel: "whatsapp", ...(account === undefined ? {} : { account }) }, false)).then(() => onAdded(number), () => undefined);
  };
  return (
    <form className="num-form" onSubmit={add}>
      <Field label="WhatsApp number">
        {theirs.length === 0 ? <p className="dash-quiet">Every number of your WhatsApp accounts already reaches an agent.</p> : <Select label="WhatsApp number" searchable={false} items={theirs.map((one) => ({ value: one.number, label: shown(one.number), detail: one.name }))} value={number} onChange={setPicked} />}
        <button type="button" className="num-link" onClick={() => setAnother(true)}>
          Connect another WhatsApp number
        </button>
      </Field>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Connecting…" disabled={number === "" || agent === ""}>
        Connect
      </Submit>
    </form>
  );
}
