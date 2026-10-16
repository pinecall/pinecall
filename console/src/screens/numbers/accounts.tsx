/** The org's accounts by what each can do — list numbers, point them here, call out — and the form that connects one more. */

import { useState, type FormEvent, type ReactNode } from "react";

import { Button, Card, Dot, Input, Label } from "../../ui";
import type { Answering, Carrier, CarrierKind, Outbound, WantedCarrier } from "./door";

const KIND_NAMED: Record<CarrierKind, string> = { twilio: "Twilio", sip: "SIP peer", whatsapp: "WhatsApp" };

const LOGO: Record<CarrierKind, string> = { twilio: "Tw", sip: "IP", whatsapp: "WA" };

/** What the tab is told: the accounts, the numbers this world routes, how calling out stands, and the two moves. */
export interface AccountsProps {
  carriers: Carrier[];
  routed: Answering[];
  outbound: Outbound | null;
  busy: boolean;
  onDrop: (account: string) => Promise<void>;
  onBring: (wanted: WantedCarrier) => Promise<void>;
}

/** The first account is born inside Add a number; this tab reads each one, connects one more, and takes one back. */
export function Accounts({ carriers, routed, outbound, busy, onDrop, onBring }: AccountsProps): ReactNode {
  const [connecting, setConnecting] = useState<"twilio" | "whatsapp" | null>(null);
  if (carriers.length === 0) {
    return (
      <Card>
        <div className="num-hero">
          <div className="num-hero-title">No account yet</div>
          <p className="num-hero-say">An account is connected the first time you add a number through it: Twilio, your PBX, or WhatsApp.</p>
        </div>
      </Card>
    );
  }
  const numbersOf = (account: string): number => routed.filter((one) => one.account === account).length;
  return (
    <>
      <div className="num-connect-more">
        {connecting === null ? (
          <>
            <Button size="xs" onClick={() => setConnecting("twilio")} disabled={busy}>
              Connect another Twilio account
            </Button>
            <Button size="xs" onClick={() => setConnecting("whatsapp")} disabled={busy}>
              Connect a WhatsApp number
            </Button>
            <span className="num-note">A PBX or another carrier is connected from Add a number.</span>
          </>
        ) : (
          <Card>
            <AccountForm kind={connecting} busy={busy} onBring={(wanted) => onBring(wanted).then(() => setConnecting(null))} />
            <div className="num-actions-flush">
              <Button size="xs" onClick={() => setConnecting(null)} disabled={busy}>
                Cancel
              </Button>
            </div>
          </Card>
        )}
      </div>
      <div className="num-accounts">
        {carriers.map((one) => (
          <div key={one.account} className="num-account">
            <div className="num-account-top">
              <span className={`num-logo num-logo-${one.kind}`}>{LOGO[one.kind]}</span>
              <span>
                <span className="num-account-name">{one.label === "" ? KIND_NAMED[one.kind] : `${KIND_NAMED[one.kind]} · ${one.label}`}</span>
                <span className="num-account-id">
                  {one.account} · {numbersOf(one.account) === 1 ? "1 number here" : `${numbersOf(one.account)} numbers here`}
                </span>
              </span>
            </div>
            <ul className="num-caps">{capabilities(one, outbound).map(([state, text]) => <Capability key={text} state={state} text={text} />)}</ul>
            <div className="num-account-foot">
              <Button size="xs" kind="danger" onClick={() => void onDrop(one.account)} disabled={busy} title="Its numbers keep ringing until each is removed.">
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="num-foot">Credentials are stored encrypted and never shown again. Removing an account leaves its numbers ringing until you remove each one.</div>
    </>
  );
}

type CapabilityState = "yes" | "waiting" | "no";

/** What an account can do, from what the gateway says of it: Twilio's API, a peer's networks and host, Meta's number. */
export function capabilities(account: Carrier, outbound: Outbound | null): [CapabilityState, string][] {
  if (account.kind === "twilio") {
    const ready = outbound?.kind === "twilio" && outbound.ready;
    return [
      ["yes", "Lists your numbers"],
      ["yes", "Points them here for you"],
      [ready ? "yes" : "no", ready ? "Calls out · ready" : "Calls out once turned on"],
    ];
  }
  if (account.kind === "whatsapp") return [["yes", "Receives messages"], ["yes", "Replies from this number"], ["no", "Calls: not on WhatsApp"]];
  const caps: [CapabilityState, string][] = [["no", "Lists numbers: a PBX cannot"]];
  for (const network of account.networks) {
    caps.push([network.state === "approved" ? "yes" : network.state === "waiting" ? "waiting" : "no", `${network.network} ${network.state === "approved" ? "admitted" : network.state === "waiting" ? "waits for the box operator" : "refused by the box operator"}`]);
  }
  return caps;
}

function Capability({ state, text }: { state: CapabilityState; text: string }): ReactNode {
  return (
    <li className={state === "no" ? "num-cap num-cap-no" : "num-cap"}>
      {state === "no" ? <span className="num-cap-off" /> : <Dot tone={state === "yes" ? "green" : "amber"} small />}
      {text}
    </li>
  );
}

/** A random password for a PBX: minted here, shown once, typed into the PBX by the person. */
export function mintedPassword(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(36).padStart(2, "0")).join("").slice(0, 24);
}

/** Connect a Twilio account or a WhatsApp number at Meta: the two kinds the sheet asks for by their credentials. */
export function AccountForm({ kind, busy, onBring }: { kind: "twilio" | "whatsapp"; busy: boolean; onBring: (wanted: WantedCarrier) => Promise<void> }): ReactNode {
  const [label, setLabel] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [user, setUser] = useState("");
  const [secret, setSecret] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [accessToken, setAccessToken] = useState("");

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    const named = label.trim() === "" ? {} : { label: label.trim() };
    void onBring(
      kind === "twilio"
        ? { kind, account_sid: accountSid.trim(), user: user.trim() || accountSid.trim(), secret, ...named }
        : { kind, phone_number_id: phoneNumberId.trim(), access_token: accessToken.trim(), ...named },
    );
  };

  return (
    <form className="num-connect" onSubmit={submit}>
      <div className="num-fields num-fields-flush">
        {kind === "twilio" ? (
          <>
            <div>
              <Label>Account SID</Label>
              <Input value={accountSid} onChange={(e) => setAccountSid(e.target.value)} placeholder="AC…" required autoComplete="off" />
            </div>
            <div>
              <Label>API key SID · or the account SID</Label>
              <Input value={user} onChange={(e) => setUser(e.target.value)} placeholder="SK…" autoComplete="off" />
            </div>
            <div>
              <Label>Secret · the key's, or the auth token</Label>
              <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} required autoComplete="new-password" />
            </div>
          </>
        ) : (
          <>
            <div>
              <Label>Phone number ID · from Meta's WhatsApp settings</Label>
              <Input value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} placeholder="1171462246041897" required autoComplete="off" />
            </div>
            <div>
              <Label>Access token · a system user's, so it does not expire</Label>
              <Input type="password" value={accessToken} onChange={(e) => setAccessToken(e.target.value)} required autoComplete="new-password" />
            </div>
          </>
        )}
        <div>
          <Label>Name · optional</Label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Clínica" autoComplete="off" />
        </div>
      </div>
      <div className="num-actions num-actions-flush">
        <Button kind="primary" type="submit" disabled={busy}>
          {busy ? "Connecting…" : `Connect ${kind === "twilio" ? "Twilio" : "WhatsApp"}`}
        </Button>
        <span className="num-note">{kind === "twilio" ? "Checked once with Twilio, stored encrypted, never shown again." : "Replies go out on this token."}</span>
      </div>
    </form>
  );
}
