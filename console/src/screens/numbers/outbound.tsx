/** Outbound calls: turned on with a plan first, then a test call, and the limits in one line. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { Button, Card, CardHead, Dot, Input, Label, Refused, Select, SelectItem, TextAction } from "../../ui";
import { Steps } from "./add-parts";
import { dial, type Outbound, type Provisioned } from "./door";

/** What the tab is told: the standing (null: no carrier yet), the agents, and the one move — planned first, then made. */
export interface OutboundPanelProps {
  outbound: Outbound | null;
  agents: HeldAgent[];
  busy: boolean;
  onProvision: (dryRun: boolean) => Promise<Provisioned>;
}

// Calling codes as a person says them. A code nobody listed is shown as the code.
const E164 = /^\+[1-9]\d{6,14}$/;

/** What is missing, in a person's words and with where to fix it. The gateway's sentence otherwise, minus any door it names. */
function missing(step: string): ReactNode {
  const said = step.toLowerCase();
  if (said.includes("no outbound trunk")) return "Outbound calls are not turned on yet.";
  if (said.includes("carrier")) {
    return (
      <>
        Connect a carrier first — <Link to="/numbers?add=">Add a number</Link>.
      </>
    );
  }
  if (said.includes("number")) {
    return (
      <>
        Add a number first — <Link to="/numbers">Numbers</Link>.
      </>
    );
  }
  return step.replace(/:?\s*(POST|PUT|GET|DELETE) \/v1\/\S+.*$/, "").trim();
}

/** The limits as one sentence. They are shown and never set here: an org that could lift its own fence would have none. */
function limits(guards: Outbound["guards"]): string {
  return [
    guards.dial_anywhere ? "Agents can call any number" : "Agents can only call numbers that already contacted you",
    `${guards.per_minute} a minute`,
    `${guards.per_day} a day`,
    `${Math.round(guards.max_duration_s / 60)} min per call`,
  ].join(" · ");
}

export function OutboundPanel({ outbound, agents, busy, onProvision }: OutboundPanelProps): ReactNode {
  const [plan, setPlan] = useState<Provisioned | null>(null);

  if (outbound === null) {
    return (
      <Card>
        <div className="num-hero">
          <div className="num-hero-title">Let your agents call people back</div>
          <p className="num-hero-say">
            Calls go out from your own numbers through your carrier account. Connect a carrier first — <Link to="/numbers?add=">Add a number</Link>.
          </p>
        </div>
      </Card>
    );
  }

  const review = (): void => void onProvision(true).then(setPlan, () => undefined);
  const confirmed = (): void => void onProvision(false).then(() => setPlan(null), () => undefined);
  const theplan = plan !== null && (
    <div className="num-plan">
      <div className="num-plan-title">What will happen — on your carrier account and on this gateway. Nothing is deleted.</div>
      <Steps steps={plan.steps} />
      <div className="num-plan-moves">
        <Button kind="primary" size="md" onClick={confirmed} disabled={busy}>
          {busy ? "Working…" : "Confirm"}
        </Button>
        <Button size="md" onClick={() => setPlan(null)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );

  if (!outbound.ready) {
    const canTurnOn = outbound.steps_missing.every((step) => step.toLowerCase().includes("no outbound trunk"));
    return (
      <Card>
        <div className="num-hero">
          <div className="num-hero-title">Let your agents call people back</div>
          <p className="num-hero-say">Calls go out from your own numbers through your carrier account.</p>
          {outbound.steps_missing.filter((step) => !step.toLowerCase().includes("no outbound trunk")).map((step) => (
            <p key={step} className="num-hero-missing">
              {missing(step)}
            </p>
          ))}
          {canTurnOn && (
            <div className="num-hero-move">
              <Button kind="primary" onClick={review} disabled={busy || plan !== null}>
                {busy && plan === null ? "Checking…" : "Turn on outbound calls"}
              </Button>
              <span className="num-note">You will see what is going to happen, and confirm.</span>
            </div>
          )}
        </div>
        {theplan}
      </Card>
    );
  }

  const [first, ...others] = outbound.from_numbers;
  return (
    <>
      <div className="num-on">
        <Dot tone="green" />
        <span>
          <b>On</b> — agents call from {prettyNumber(first)}
          {others.length > 0 && ` and ${others.length} more`}
        </span>
      </div>

      <TestCall agents={agents} from={outbound.from_numbers} />

      <div className="num-limits">
        <div>
          <div className="num-limits-say">{limits(outbound.guards)}</div>
          <div className="num-limits-who">Limits are set by whoever runs this gateway.</div>
        </div>
        <TextAction onClick={review} disabled={busy || plan !== null}>
          Repair the setup
        </TextAction>
      </div>
      {plan !== null && <Card>{theplan}</Card>}
    </>
  );
}

/** One real call, placed as an agent: the way to hear that outbound works. */
function TestCall({ agents, from }: { agents: HeldAgent[]; from: string[] }): ReactNode {
  const credentials = useCredentials();
  const [agent, setAgent] = useState(agents[0]?.slug ?? "");
  const [to, setTo] = useState("");
  const [line, setLine] = useState(from[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [placed, setPlaced] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    if (agent === "" && agents[0] !== undefined) setAgent(agents[0].slug);
  }, [agents, agent]);

  const call = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const number = to.replace(/[\s()-]/g, "");
    setPlaced(null);
    if (!E164.test(number)) {
      setRefused("Write the number with its country code, like +34600000000.");
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      setPlaced(await dial(credentials, agent, number, from.length > 1 ? line : undefined));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHead title="Make a test call" meta="the agent rings the number and talks when it is answered" />
      <form onSubmit={(event) => void call(event)}>
        <div className={from.length > 1 ? "num-fields num-fields-3" : "num-fields"}>
          <div>
            <Label>Agent</Label>
            <Select value={agent} onValueChange={(value) => setAgent(value)} required>
              {agents.map((held) => (
                <SelectItem key={held.slug} value={held.slug}>
                  {held.slug}
                </SelectItem>
              ))}
            </Select>
          </div>
          <div>
            <Label>Number to call</Label>
            <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="+34 600 000 000" required autoComplete="off" />
          </div>
          {from.length > 1 && (
            <div>
              <Label>From</Label>
              <Select value={line} onValueChange={(value) => setLine(value)}>
                {from.map((one) => (
                  <SelectItem key={one} value={one}>
                    {prettyNumber(one)}
                  </SelectItem>
                ))}
              </Select>
            </div>
          )}
        </div>
        <div className="num-actions">
          <Button kind="primary" type="submit" disabled={busy || agent === ""}>
            {busy ? "Calling…" : "Call"}
          </Button>
          {placed !== null && (
            <span className="num-placed">
              Ringing. <Link to={`/calls/${placed}`}>Watch it live</Link>
            </span>
          )}
        </div>
        {refused !== null && (
          <div className="num-refused">
            <Refused>{refused}</Refused>
          </div>
        )}
      </form>
    </Card>
  );
}
