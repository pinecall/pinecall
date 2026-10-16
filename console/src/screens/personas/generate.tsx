/** Callers written for the agent by the judge model: about what, after whom — then each one kept or not. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Field, Pill, Refused, Select, SelectItem, TextArea } from "../../ui";
import { generatePersonas, isPinecalls, writePersona, type Persona, type ProposedPersona } from "./door";
import { Face } from "./face";

/**
 * Two questions and a button: what the callers call about, and which of Pinecall's they take
 * after; the gateway writes as many as it writes unless asked (three). What comes back is drawn as the callers of the grid are, each with what it
 * wants, how it talks and what it holds the agent to, and is saved only when kept.
 */
export function Generate({ agent, personas, onKept, onCancel }: { agent: string; personas: Persona[]; onKept: (personas: Persona[]) => void; onCancel: () => void }): ReactNode {
  const credentials = useCredentials();
  const [about, setAbout] = useState("");
  const [template, setTemplate] = useState("");
  const [written, setWritten] = useState<ProposedPersona[]>([]);
  const [bill, setBill] = useState<string | null>(null);
  const [kept, setKept] = useState<string[]>([]);
  const [writing, setWriting] = useState(false);
  const [keeping, setKeeping] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const library = personas.filter(isPinecalls);

  const write = async (): Promise<void> => {
    setWriting(true);
    setRefused(null);
    try {
      const made = await generatePersonas(credentials, agent, { ...(about.trim() === "" ? {} : { about: about.trim() }), ...(template === "" ? {} : { template }) });
      setWritten(made.personas);
      setKept([]);
      setBill(made.evals === 0 ? "on your own judge key, not billed" : `${made.evals} eval${made.evals === 1 ? "" : "s"} · $${made.cost_usd.toFixed(4)}`);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setWriting(false);
    }
  };

  // One at a time, in order: each keep answers the agent's callers as they stand after it.
  const keep = async (these: readonly ProposedPersona[]): Promise<void> => {
    setKeeping(true);
    setRefused(null);
    try {
      for (const one of these) {
        const { name, ...rest } = one;
        onKept(await writePersona(credentials, agent, name, rest));
        setKept((before) => [...before, name]);
      }
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setKeeping(false);
    }
  };

  const waiting = written.filter((one) => !kept.includes(one.name));

  return (
    <article className="psn-doc">
      <header className="psn-doc-head">
        <div>
          <h1 className="psn-doc-name">Generate callers</h1>
          <p className="psn-doc-about">
            A model reads {agent} — its prompt, its tools, what it knows — and writes callers to put it to the test, each with what it expects the agent to do. You choose which to keep; nothing is saved before.
          </p>
        </div>
        <div className="psn-doc-actions">
          <Button size="sm" onClick={onCancel}>
            Close
          </Button>
        </div>
      </header>

      <section className="psn-gen-form" aria-label="what to write">
        <Field label="What they call about" grow>
          <TextArea rows={2} value={about} placeholder="Optional — price questions, moving an appointment, a caller in a hurry. Left empty, the model picks from what the agent does." onChange={(event) => setAbout(event.target.value)} />
        </Field>
        <Field label="Modelled on">
          <Select aria-label="Modelled on one of Pinecall's callers" value={template} onValueChange={setTemplate}>
            <SelectItem value="">Nobody in particular</SelectItem>
            {library.map((one) => (
              <SelectItem key={one.name} value={one.name}>
                {one.name}
              </SelectItem>
            ))}
          </Select>
          <p className="psn-gen-hint">One of Pinecall's callers to take after: its manner and its kind of trouble.</p>
        </Field>
        <footer className="psn-gen-go">
          <span className="psn-gen-cost">
            One eval a caller written, none on your own judge key.
          </span>
          <Button kind="primary" disabled={writing || keeping} onClick={() => void write()}>
            {writing ? "Writing…" : written.length === 0 ? "Write callers" : "Write again"}
          </Button>
        </footer>
      </section>

      {writing && <p className="psn-gen-wait">Reading {agent} and writing callers for it. It takes a few seconds.</p>}
      <Refused>{refused}</Refused>

      {written.length > 0 && !writing && (
        <section className="ui-tiles-block" aria-label="callers written">
          <div className="psn-gen-head">
            <span className="psn-gen-said">
              {written.length} {written.length === 1 ? "caller" : "callers"} written{bill === null ? "" : ` · ${bill}`}
            </span>
            {waiting.length > 0 && (
              <Button size="sm" disabled={keeping} onClick={() => void keep(waiting)}>
                {keeping ? "Keeping…" : waiting.length === written.length ? "Keep all" : `Keep the other ${waiting.length}`}
              </Button>
            )}
          </div>
          <div className="ui-tiles">
            {written.map((one) => (
              <Written key={one.name} caller={one} kept={kept.includes(one.name)} busy={keeping} onKeep={() => void keep([one])} />
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

function Written({ caller, kept, busy, onKeep }: { caller: ProposedPersona; kept: boolean; busy: boolean; onKeep: () => void }): ReactNode {
  return (
    <article className={kept ? "ui-tile psn-gen-kept" : "ui-tile"}>
      <div className="ui-tile-top">
        <Face name={caller.name} size={56} />
        {kept ? (
          <Pill tone="green" small>
            kept
          </Pill>
        ) : (
          <Button size="sm" disabled={busy} onClick={onKeep}>
            Keep
          </Button>
        )}
      </div>
      <h3 className="ui-tile-name">{caller.name}</h3>
      {caller.about !== "" && <p className="psn-gen-about">{caller.about}</p>}
      <dl className="psn-gen-facts">
        <dt>Wants</dt>
        <dd>{caller.goal}</dd>
        {caller.style !== "" && (
          <>
            <dt>Sounds</dt>
            <dd>{caller.style}</dd>
          </>
        )}
      </dl>
      {caller.expects.length > 0 && (
        <>
          <p className="psn-gen-label">Holds the agent to</p>
          <ul className="psn-expects">
            {caller.expects.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
      {caller.tags.length > 0 && (
        <div className="ui-tile-tags">
          {caller.tags.map((tag) => (
            <Pill key={tag} tone={tag === "red-team" ? "red" : "gray"} small>
              {tag}
            </Pill>
          ))}
        </div>
      )}
    </article>
  );
}
