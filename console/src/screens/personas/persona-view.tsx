/** One persona, read: who they are, what they want, how they talk, what they know — and what to do with them. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Link } from "react-router";
import { Button, ButtonLink } from "../../ui";
import { dayAndTime } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { dropPersona, isPinecalls, playPersona, switchPersona, type Persona } from "./door";
import { Face } from "./face";
import { PlayedBy, type Played } from "./played-by";

// Unset is the runtime's choice, which is not the same as nothing: it picks the model, and a voice
// the agent does not have.
const THE_RUNTIMES = "the runtime's choice";

// What plays behind the caller, in the words the page uses.
const BACKGROUND_SAID: Record<string, string> = { television: "a television", cafe: "a café", office: "an office", street: "a street" };

export function PersonaView({
  inView,
  persona,
  fixed,
  onEdit,
  onDropped,
  onSwitched,
}: {
  /** The agent in view, or "" for every agent: where "Use in a simulation" opens Simulations. */
  inView: string;
  persona: Persona;
  /** The class owns the roster: the caller is read here and written in the repository. */
  fixed: boolean;
  onEdit: () => void;
  onDropped: (personas: Persona[]) => void;
  /** One of Pinecall's switched: the agent's list after it, the caller staying open. */
  onSwitched: (personas: Persona[]) => void;
}): ReactNode {
  const credentials = useCredentials();
  // Delete asks twice: the file goes, and a persona nobody committed yet has no other copy.
  const [armed, setArmed] = useState(false);
  // The confirm is disarmed and the button shut the moment the door is knocked at, so the second
  // press of an impatient double-click — or of a slow answer — cannot send a second DELETE.
  const [dropping, setDropping] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // One of Pinecall's is played as the agent says: its model and its voice; empty is the runtime's.
  const was: Played = { llm: persona.llm ?? "", tts: persona.tts ?? "", voice: persona.voice ?? "" };
  const [played, setPlayed] = useState<Played>(was);
  const moved = played.llm !== was.llm || played.tts !== was.tts || played.voice !== was.voice;
  const facts = Object.entries(persona.facts);

  const drop = async (): Promise<void> => {
    if (dropping) return;
    setDropping(true);
    setArmed(false);
    setRefused(null);
    try {
      onDropped(await dropPersona(credentials, persona.agent, persona.name));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setDropping(false);
    }
  };

  // One of Pinecall's is never written nor dropped: it is on for the agent's nightly, or off.
  const flip = async (): Promise<void> => {
    setDropping(true);
    setRefused(null);
    try {
      onSwitched(await switchPersona(credentials, persona.agent, persona.name, !persona.on));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setDropping(false);
    }
  };

  const remodel = async (): Promise<void> => {
    setDropping(true);
    setRefused(null);
    try {
      onSwitched(await playPersona(credentials, persona.agent, persona.name, played));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setDropping(false);
    }
  };

  return (
    <article className="psn-doc">
      <Link className="psn-back" to={rowAt(inView, "personas")}>
        ← All personas
      </Link>
      <header className="psn-doc-head">
        <div className="psn-doc-who">
          <Face name={persona.name} size={64} />
          <div>
            <h1 className="psn-doc-name">{persona.name}</h1>
            {persona.about !== "" && <p className="psn-doc-about">{persona.about}</p>}
          </div>
        </div>
        <div className="psn-doc-actions">
          <ButtonLink kind="primary" size="sm" to={`${rowAt(inView, "simulations")}?agent=${encodeURIComponent(persona.agent)}&persona=${encodeURIComponent(persona.name)}`}>
            Use in a simulation
          </ButtonLink>
          {fixed ? null : isPinecalls(persona) ? (
            <Button size="sm" disabled={dropping} onClick={() => void flip()}>
              {persona.on ? "Switch off" : "Switch on"}
            </Button>
          ) : (
            <>
              <Button size="sm" onClick={onEdit}>
                Edit
              </Button>
              <Button size="sm" kind="danger" disabled={dropping} onClick={() => (armed ? void drop() : setArmed(true))} onBlur={() => setArmed(false)}>
                {dropping ? "Deleting…" : armed ? "Delete · sure?" : "Delete"}
              </Button>
            </>
          )}
        </div>
      </header>
      {fixed && (
        <p className="psn-doc-note">
          Set by the class of {persona.agent}: {isPinecalls(persona) ? `${persona.on ? "on" : "off"} in its personas({ on })` : `the file agents/${persona.agent}/test/personas/${persona.name}.json`}. The class&apos;s declaration wins: change it in the code, or take
          `personas` out of the class to write callers here.
        </p>
      )}

      <Section title="What they want" hint="The goal the model pursues on every turn, until it has it or sees it will not.">
        <p className="psn-doc-text">{persona.goal}</p>
      </Section>
      <Section title="How they talk" hint="The manner: hurried, polite, switching language mid-sentence. It shapes every line, not what they ask for.">
        <p className="psn-doc-text">{persona.style}</p>
      </Section>
      <Section title="What they expect of the agent" hint="The expected-outcome judge holds every call of theirs to these at hang-up; the model playing them is never told.">
        {persona.expects.length === 0 ? (
          <p className="psn-doc-none">Nothing: the expected-outcome judge answers N/A on their calls.</p>
        ) : (
          <ul className="psn-expects">
            {persona.expects.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="How they act on a spoken line" hint="Talking over the agent tests its barge-in; a pause tests its patience.">
        <dl className="psn-facts">
          <div className="psn-fact">
            <dt>talks over</dt>
            <dd>{persona.behavior.interrupts === 0 ? "never" : `${Math.round(persona.behavior.interrupts * 100)}% of the answers`}</dd>
          </div>
          <div className="psn-fact">
            <dt>pauses</dt>
            <dd>{persona.behavior.pause_s === 0 ? "never" : `${persona.behavior.pause_s}s before each line`}</dd>
          </div>
          <div className="psn-fact">
            <dt>murmurs</dt>
            <dd>{persona.behavior.backchannels === 0 ? "never" : `into ${Math.round(persona.behavior.backchannels * 100)}% of the answers`}</dd>
          </div>
          <div className="psn-fact">
            <dt>speaks</dt>
            <dd>{persona.behavior.speed === 1 ? "as the voice reads it" : `at ${persona.behavior.speed}× the voice's tempo`}</dd>
          </div>
          <div className="psn-fact">
            <dt>behind them</dt>
            <dd>{persona.behavior.interferer_db === null ? "a quiet room" : `${BACKGROUND_SAID[persona.behavior.ambience]}, ${persona.behavior.interferer_db} dB under them`}</dd>
          </div>
        </dl>
      </Section>
      <Section title="How they are played" hint="The model that improvises them and the voice their lines are read in, in an agent's own words.">
        {!isPinecalls(persona) && (
        <dl className="psn-facts">
          {(
            [
              ["model", persona.llm],
              ["voice vendor", persona.tts],
              ["voice", persona.voice],
            ] as const
          ).map(([what, said]) => (
            <div key={what} className="psn-fact">
              <dt>{what}</dt>
              <dd>{said ?? THE_RUNTIMES}</dd>
            </div>
          ))}
        </dl>
        )}
        {isPinecalls(persona) && (
          <form
            className="psn-model"
            onSubmit={(event) => {
              event.preventDefault();
              void remodel();
            }}
          >
            <PlayedBy played={played} onChange={setPlayed} />
            <Button size="sm" type="submit" disabled={dropping || !moved || fixed}>
              Save how they are played
            </Button>
          </form>
        )}
      </Section>
      <Section title="What they know about themselves" hint="The only facts they may state. Asked for anything else, they say they do not know — they never invent.">
        {facts.length === 0 ? (
          <p className="psn-doc-none">Nothing: this caller states no fact about themselves.</p>
        ) : (
          <dl className="psn-facts">
            {facts.map(([what, said]) => (
              <div key={what} className="psn-fact">
                <dt>{what}</dt>
                <dd>{said}</dd>
              </div>
            ))}
          </dl>
        )}
      </Section>

      <footer className="psn-doc-foot">
        <span className="psn-doc-note">
          {persona.owner === "pinecall"
            ? `One of Pinecall's personas${persona.summary ? `: ${persona.summary}` : ""} — ${persona.on ? "on" : "off"} for this agent.`
            : persona.author == null || persona.author === "" || persona.set_at == null
              ? "Kept by the gateway."
              : `Last written by ${persona.author}, ${dayAndTime(persona.set_at)}.`}
          {Object.keys(persona.state).length > 0 && " It opens the call in a state, written from a project."}
        </span>
      </footer>
      {refused !== null && <p className="psn-refused">{refused}</p>}
    </article>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }): ReactNode {
  return (
    <section className="psn-sec">
      <h2 className="psn-sec-title">{title}</h2>
      <p className="psn-sec-hint">{hint}</p>
      {children}
    </section>
  );
}
