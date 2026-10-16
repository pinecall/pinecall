/** Form to run a suite: pick goldens and line conditions. */

import { useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Check, Input, Label, Refused } from "../../ui";
import { finalChecks } from "./golden-words";
import { startSuite, type Listed, type Roster } from "./testing";

// Same defaults as `pinecall test --voice`.
const NOISE_DB = 15;
const LOSS_PERCENT = 0;

/**
 * Runs the same suite as `pinecall test`, through the class of the directory `pinecall start`
 * runs in; only that process can start it.
 */
export function SuiteForm({ agent, roster, onOpened }: { agent: string; roster: Roster; onOpened: (run: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [ticked, setTicked] = useState<Set<string>>(() => new Set(roster.goldens.map((one) => one.name)));
  const [models, setModels] = useState("");
  const [voice, setVoice] = useState(false);
  const [spoiled, setSpoiled] = useState(false);
  const [noise, setNoise] = useState(NOISE_DB);
  const [loss, setLoss] = useState(LOSS_PERCENT);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const tick = (name: string, on: boolean): void => {
    const next = new Set(ticked);
    if (on) next.add(name);
    else next.delete(name);
    setTicked(next);
  };
  const all = ticked.size === roster.goldens.length;

  const run = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setStarting(true);
    setRefused(null);
    try {
      const asked = models
        .split(",")
        .map((one) => one.trim())
        .filter((one) => one !== "");
      const opened = await startSuite(credentials, {
        agent,
        goldens: roster.goldens.map((one) => one.name).filter((name) => ticked.has(name)),
        ...(asked.length === 0 ? {} : { models: asked }),
        voice,
        ...(voice && spoiled ? { background_noise: noise, packet_loss: loss / 100 } : {}),
      });
      onOpened(opened);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setStarting(false);
    }
  };

  return (
    <Card>
      <CardHead title="Run a suite" />
      <form onSubmit={(event) => void run(event)}>
        <div className="ev-suite-controls">
          <div className="ev-suite-models">
            <Label>Models</Label>
            <Input size="sm" value={models} placeholder="the one the settings name · vendor/model, comma separated" onChange={(event) => setModels(event.target.value)} />
          </div>
          <Check checked={voice} onChange={setVoice}>
            Out loud
          </Check>
          {voice && (
            <Check checked={spoiled} onChange={setSpoiled}>
              Noisy line
            </Check>
          )}
          {voice && spoiled && (
            <>
              <div className="ev-suite-number">
                <Label>Noise, dB under</Label>
                <Input size="sm" type="number" min={0} max={60} value={noise} onChange={(event) => setNoise(Number(event.target.value))} />
              </div>
              <div className="ev-suite-number">
                <Label>Packets lost, %</Label>
                <Input size="sm" type="number" min={0} max={100} value={loss} onChange={(event) => setLoss(Number(event.target.value))} />
              </div>
            </>
          )}
          <Button kind="primary" size="md" type="submit" className="ev-suite-go" disabled={starting || ticked.size === 0}>
            {starting ? "Opening…" : `Run ${all ? "the suite" : `${ticked.size} golden${ticked.size === 1 ? "" : "s"}`}`}
          </Button>
        </div>
        <div className="ev-suite-all">
          <Check checked={all} onChange={(on) => setTicked(new Set(on ? roster.goldens.map((one) => one.name) : []))}>
            {ticked.size} of {roster.goldens.length}
          </Check>
        </div>
        {roster.goldens.map((golden) => (
          <div key={golden.name} className="ev-suite-golden">
            <Check checked={ticked.has(golden.name)} onChange={(on) => tick(golden.name, on)}>
              <span className="ev-suite-name">{golden.name}</span>
            </Check>
            <span className="ev-suite-says ui-clip">{firstSaid(golden)}</span>
            <span className="ev-suite-expects ui-clip">{shapeOf(golden)}</span>
          </div>
        ))}
      </form>
      <Refused>{refused}</Refused>
    </Card>
  );
}

// The caller's first line, which is what a person recognises a golden by.
function firstSaid(golden: Listed): string {
  const said = (golden.turns ?? []).find((turn) => turn.say !== undefined && turn.say !== null)?.say;
  return said === undefined || said === null ? "" : `“${said}”`;
}

// How long it is and how much it checks: "3 turns · 5 steps · 2 at the end".
function shapeOf(golden: Listed): string {
  const turns = golden.turns ?? [];
  const steps = turns.reduce((sum, turn) => sum + (turn.then ?? []).length, 0);
  const finals = finalChecks(golden.expect).length;
  return [`${String(turns.length)} ${turns.length === 1 ? "turn" : "turns"}`, `${String(steps)} ${steps === 1 ? "step" : "steps"}`, ...(finals === 0 ? [] : [`${String(finals)} at the end`])].join(" · ");
}
