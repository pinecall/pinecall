/** Who was on the line, model by model: the agent's ears, thinking and voice as its call ran them, and on a simulated call the persona's own. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { usd } from "../../lib/format";
import { readSimulation, type PersonaRun } from "../personas/door";

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

/** The agent's three stages as the call ran them, read off the metrics the log carries. */
export function agentModels(state: State): { hears: Ran | null; thinks: Ran | null; speaks: Ran | null } {
  const heard = state.turns.flatMap((turn) => (turn.role === "user" && turn.metrics.stt_metadata?.model_name ? [{ metadata: turn.metrics.stt_metadata }] : []));
  return {
    hears: lastNamed(state.metrics.stt) ?? lastNamed(heard),
    thinks: lastNamed(state.metrics.llm) ?? lastNamed(state.metrics.realtime),
    speaks: lastNamed(state.metrics.tts),
  };
}

/** The persona a call was played by, as its call.started names it; null for a person's call. */
export function personaOf(entries: readonly Entry[]): string | null {
  const started = entries.find((entry) => entry.type === "call.started");
  const persona = started?.data["persona"];
  return typeof persona === "string" && persona !== "" ? persona : null;
}

export function Models({ call, state, entries }: { call: string; state: State; entries: readonly Entry[] }): ReactNode {
  const credentials = useCredentials();
  const persona = personaOf(entries);
  const [run, setRun] = useState<PersonaRun | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const over = state.status === "ended";
  useEffect(() => {
    if (persona === null) return;
    let live = true;
    // Read again once the call is over: what the caller cost is kept when the simulation ends.
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
  return (
    <section className="call-side-part" aria-label="the models on the line">
      <h3 className="call-side-head">Models</h3>
      <dl className="call-models">
        <Line role="Agent hears" ran={agent.hears} />
        <Line role="Agent thinks" ran={agent.thinks} />
        <Line role="Agent speaks" ran={agent.speaks} />
        {persona !== null && (
          <>
            <dt className="call-models-who">{persona}</dt>
            <dd className="call-models-who-sub">{run !== null && run.caller_cost_usd > 0 ? `the simulated caller · ${usd(run.caller_cost_usd)}` : "the simulated caller"}</dd>
            <Line role="Caller thinks" ran={played?.llm == null ? null : { model: played.llm, provider: null }} />
            {played?.tts != null && <Line role="Caller speaks" ran={{ model: played.voice ? `${played.tts} · ${played.voice}` : played.tts, provider: null }} />}
            {played === null && <dd className="call-models-none">{refused ?? (run === null ? "Reading who played it…" : "Not kept for a call this old.")}</dd>}
          </>
        )}
      </dl>
    </section>
  );
}

function Line({ role, ran }: { role: string; ran: Ran | null }): ReactNode {
  return (
    <>
      <dt className="call-models-role">{role}</dt>
      <dd className="call-models-model" title={ran?.provider ?? undefined}>
        {ran === null ? <span className="call-models-none">—</span> : ran.model}
      </dd>
    </>
  );
}
