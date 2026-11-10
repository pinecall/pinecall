/** Who was on the line, model by model: the agent's ears, thinking and voice as its call ran them, and on a simulated call the persona's own. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { readSimulation, type PersonaRun } from "./door";
import { usd } from "./format";

/** A model as livekit named it on its metrics; null before the stage first ran. */
interface Ran {
  model: string;
  provider: string | null;
}

interface Named {
  model_name?: string | null | undefined;
  model_provider?: string | null | undefined;
}

// The newest block that names its model: a fallback taking over is the model the call runs on now.
function lastNamed(blocks: readonly { metadata?: Named | null | undefined }[]): Ran | null {
  for (let at = blocks.length - 1; at >= 0; at -= 1) {
    const named = blocks[at]?.metadata;
    if (named?.model_name) return { model: named.model_name, provider: named.model_provider ?? null };
  }
  return null;
}

function agentModels(state: State): { hears: Ran | null; thinks: Ran | null; speaks: Ran | null } {
  const heard = state.turns.flatMap((turn) => (turn.role === "user" && turn.metrics.stt_metadata?.model_name ? [{ metadata: turn.metrics.stt_metadata }] : []));
  return { hears: lastNamed(state.metrics.stt) ?? lastNamed(heard), thinks: lastNamed(state.metrics.llm) ?? lastNamed(state.metrics.realtime), speaks: lastNamed(state.metrics.tts) };
}

function personaOf(entries: readonly Entry[]): string | null {
  const persona = entries.find((entry) => entry.type === "call.started")?.data["persona"];
  return typeof persona === "string" && persona !== "" ? persona : null;
}

function Line({ role, ran }: { role: string; ran: Ran | null }): ReactNode {
  return (
    <div className="calls-model">
      <span className="dash-quiet">{role}</span>
      <span className={ran === null ? "calls-model-name dash-clip dash-quiet" : "calls-model-name dash-clip"} title={ran === null ? undefined : [ran.provider, ran.model].filter(Boolean).join(", ")}>
        {ran === null ? "—" : ran.model}
      </span>
    </div>
  );
}

export function Models({ call, state, entries }: { call: string; state: State; entries: readonly Entry[] }): ReactNode {
  const credentials = useCredentials();
  const persona = personaOf(entries);
  const [run, setRun] = useState<PersonaRun | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const over = state.status === "ended";

  // Read again once the call is over: what the caller cost is kept when the simulation ends.
  useEffect(() => {
    if (persona === null) return;
    let live = true;
    readSimulation(credentials, call).then(
      (read) => live && setRun(read),
      (failed: unknown) => live && setRefused(saidBy(failed)),
    );
    return () => {
      live = false;
    };
  }, [credentials, call, persona, over]);

  const agent = agentModels(state);
  const played = run?.played_by ?? null;
  const cost = run !== null && run.caller_cost_usd > 0 ? usd(run.caller_cost_usd) : null;
  return (
    <>
      <section className="calls-part" aria-label="The models on the line">
        <span className="dash-eyebrow">Models</span>
        <div className="calls-models">
          <Line role="Hears" ran={agent.hears} />
          <Line role="Thinks" ran={agent.thinks} />
          <Line role="Speaks" ran={agent.speaks} />
        </div>
      </section>
      {persona !== null && (
        <section className="calls-part" aria-label="Who played the caller">
          <div className="calls-part-top">
            <span className="dash-eyebrow">Simulated caller</span>
            {cost !== null && <span className="dash-quiet">{cost}</span>}
          </div>
          <div className="calls-models">
            <div className="calls-model">
              <span className="dash-quiet">Persona</span>
              <span className="calls-model-name dash-clip">{persona}</span>
            </div>
            {played === null ? (
              <p className="dash-quiet">{refused ?? (run === null ? "Reading who played it…" : "Its models were not kept for a call this old.")}</p>
            ) : (
              <>
                <Line role="Thinks" ran={played.llm === null ? null : { model: played.llm, provider: null }} />
                {played.tts !== null && <Line role="Speaks" ran={{ model: played.voice ? `${played.tts}, ${played.voice}` : played.tts, provider: null }} />}
              </>
            )}
          </div>
        </section>
      )}
    </>
  );
}
