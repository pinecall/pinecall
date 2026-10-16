/** Memory screen: stored caller facts, forgetting a contact, and the memory goldens. */

import { type ContactFact, type ExtractionRun, type MemoryScore } from "@pinecall/core/wire/rest-retrieval";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { dayOf } from "../../lib/format";
import { Button, Card, CardHead, Empty, Input, Page, PageHead, Refused, TableHead, TextAction } from "../../ui";
import { askRecall, dropFact, forgetContact, readAgentMemory, readContact, readHere, runExtraction, type AgentFact, type Here } from "./door";
import "./memory.css";

const COLUMNS = "150px minmax(0,1fr) 110px 76px";

/** Display form of a contact: phone number or app-provided id. */
function callerOf(contact: string): string {
  return contact.startsWith("+") ? prettyNumber(contact) : contact;
}

/**
 * Facts come from the gateway; goldens (`memory/golden.json`, `test/memory`) are files in the
 * directory `pinecall start` runs in, so they go through that process.
 */
export function Memory(): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const [every, setEvery] = useState<AgentFact[] | null | undefined>(undefined);
  const [contact, setContact] = useState("");
  const [looked, setLooked] = useState<{ contact: string; facts: ContactFact[] } | null>(null);
  const [forgotten, setForgotten] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const rereadEvery = useCallback(async (): Promise<void> => {
    setEvery(await readAgentMemory(credentials, agent));
  }, [credentials, agent]);

  useEffect(() => {
    let gone = false;
    readAgentMemory(credentials, agent).then(
      (facts) => {
        if (!gone) setEvery(facts);
      },
      (failed: unknown) => {
        if (!gone) {
          setEvery(null);
          setRefused(saidBy(failed));
        }
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const look = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const who = contact.trim();
    setRefused(null);
    setForgotten(null);
    try {
      setLooked({ contact: who, facts: (await readContact(credentials, who)).facts });
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  // Erasing cannot be undone, so confirm inline before it happens.
  const forget = async (who: string): Promise<void> => {
    if (!window.confirm(`Erase everything memory kept about ${who}? There is no undo.`)) return;
    setRefused(null);
    try {
      const gone = (await forgetContact(credentials, who)).forgotten;
      setForgotten(`${gone} fact${gone === 1 ? "" : "s"} about ${callerOf(who)} forgotten.`);
      setLooked({ contact: who, facts: [] });
      if (every !== null && every !== undefined) await rereadEvery();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const drop = async (fact: AgentFact): Promise<void> => {
    if (!window.confirm(`Drop "${fact.text}"? The rest of what memory keeps about ${callerOf(fact.contact)} stays.`)) return;
    setRefused(null);
    try {
      await dropFact(credentials, fact.id);
      await rereadEvery();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const listing = every !== null && every !== undefined;
  const shown = listing ? every.filter((fact) => contact.trim() === "" || fact.contact.includes(contact.trim())) : [];

  return (
    <Page width={900} tight>
      <PageHead
        title="Memory"
        ledeWidth={620}
        lede="What this agent carries between calls with the same caller — written by the agent, readable here, and droppable one row at a time."
      />

      <Card>
        <CardHead title="Callers">
          <form className="mem-look" onSubmit={(event) => void look(event)}>
            <Input size="sm" value={contact} placeholder="Look up a caller — a number or an id" onChange={(event) => setContact(event.target.value)} />
            {!listing && (
              <Button size="sm" type="submit" disabled={contact.trim() === ""}>
                Look up
              </Button>
            )}
            {looked !== null && looked.facts.length > 0 && (
              <Button size="sm" kind="danger" onClick={() => void forget(looked.contact)}>
                Forget
              </Button>
            )}
          </form>
        </CardHead>

        {forgotten !== null && <div className="ui-card-foot">{forgotten}</div>}

        {listing ? (
          shown.length === 0 ? (
            <Empty>{every.length === 0 ? "Memory keeps nothing about any caller of this agent yet." : "No caller matches."}</Empty>
          ) : (
            <>
              <TableHead columns={COLUMNS} labels={["Caller", "Remembered", "Written", "Action>"]} />
              {shown.map((fact) => (
                <div key={fact.id} className="ui-table-row" style={{ gridTemplateColumns: COLUMNS }}>
                  <span className="mem-caller ui-clip" title={fact.contact}>
                    {callerOf(fact.contact)}
                  </span>
                  <span className="mem-fact">{fact.text}</span>
                  <span className="ui-cell-faint">{dayOf(fact.written_at)}</span>
                  <span className="ui-cell-end">
                    <TextAction danger onClick={() => void drop(fact)}>
                      Drop
                    </TextAction>
                  </span>
                </div>
              ))}
            </>
          )
        ) : looked === null ? (
          <Empty>Look up a caller by the number they called from, or by the id your app named them with, to read what memory keeps about them.</Empty>
        ) : looked.facts.length === 0 ? (
          <Empty>Memory keeps nothing about {callerOf(looked.contact)}.</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["Caller", "Remembered", "Written", "Category>"]} />
            {looked.facts.map((fact, at) => (
              <div key={fact.id ?? `${at}`} className={fact.invalidated_at === null ? "ui-table-row" : "ui-table-row mem-gone"} style={{ gridTemplateColumns: COLUMNS }}>
                <span className="mem-caller ui-clip">{callerOf(looked.contact)}</span>
                <span className="mem-fact">
                  {fact.text}
                  {fact.invalidated_at !== null && <span className="mem-superseded"> · superseded {dayOf(fact.invalidated_at)}</span>}
                </span>
                <span className="ui-cell-faint">{dayOf(fact.valid_from)}</span>
                <span className="ui-cell-faint ui-clip mem-category">{fact.category ?? "—"}</span>
              </div>
            ))}
          </>
        )}
      </Card>

      <Refused>{refused}</Refused>

      <Goldens agent={agent} />
    </Page>
  );
}

/** Recall and extraction goldens of the agent's directory. */
function Goldens({ agent }: { agent: string }): ReactNode {
  const credentials = useCredentials();
  const [here, setHere] = useState<Here | null>(null);
  const [away, setAway] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [score, setScore] = useState<MemoryScore | null>(null);
  const [extraction, setExtraction] = useState<ExtractionRun | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readHere(credentials, agent).then(
      (read) => {
        if (!gone) setHere(read);
      },
      (failed: unknown) => {
        if (!gone) setAway(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const run = async (which: "recall" | "extraction"): Promise<void> => {
    setBusy(which);
    setRefused(null);
    try {
      if (which === "recall") setScore(await askRecall(credentials, agent));
      else setExtraction(await runExtraction(credentials, agent));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy("");
    }
  };

  if (here === null) {
    return away === null ? null : (
      <Card>
        <CardHead title="The goldens of this directory" />
        <Empty>They are read by the process holding {agent}, and it did not answer: {away}.</Empty>
      </Card>
    );
  }
  if (here.agent !== agent) {
    return (
      <Card>
        <CardHead title="The goldens of this directory" />
        <Empty>
          {here.agent === null
            ? "No agent class in the directory the agent's `pinecall start` runs in, so its goldens are not here."
            : `The process holding the agent runs in ${here.agent}'s directory: to run ${agent}'s memory goldens, run \`pinecall start\` there.`}
        </Empty>
      </Card>
    );
  }

  return (
    <>
      <div className="mem-goldens">
        <Card>
          <CardHead title="Recall" meta={`${here.questions} questions`} />
          <div className="mem-run">
            <p className="mem-say">Every question asked of the ranking, scored by code with no model. No contact of yours is read: each question brings its own facts to a scratch contact.</p>
            <Button size="md" disabled={busy !== "" || here.questions === 0} onClick={() => void run("recall")}>
              {busy === "recall" ? "Asking…" : "Run it"}
            </Button>
          </div>
          {score !== null && (
            <>
              <div className="mem-figures">
                <Figure label={`recall@${score.k}`} value={score.recall_at_k.toFixed(2)} />
                <Figure label="nDCG@10" value={score.ndcg_at_10.toFixed(2)} />
                <Figure label="missed" value={String(score.misses.length)} />
              </div>
              {score.misses.map((missed) => (
                <div key={missed.asks} className="mem-miss">
                  <div className="mem-miss-asks">{missed.asks}</div>
                  <div className="mem-miss-why">
                    wanted {missed.missing.join(", ")} · got {missed.found[0] ?? "nothing"}
                  </div>
                </div>
              ))}
            </>
          )}
        </Card>

        <Card>
          <CardHead title="Extraction" meta={`${here.cases.length} cases`} />
          <div className="mem-run">
            <p className="mem-say">One call written down per case, and one model call each — the very one a hang-up makes. Which categories got a fact, which never did, what must not survive.</p>
            <Button size="md" disabled={busy !== "" || here.cases.length === 0} onClick={() => void run("extraction")}>
              {busy === "extraction" ? "Running…" : "Run them"}
            </Button>
          </div>
          {extraction !== null && (
            <>
              <div className="mem-figures">
                <Figure label="held" value={`${extraction.held}/${extraction.cases}`} />
                <Figure label="model" value={extraction.model} />
              </div>
              {extraction.results
                .filter((one) => !one.held)
                .map((one) => (
                  <div key={one.name} className="mem-miss">
                    <div className="mem-miss-asks">{one.name}</div>
                    <div className="mem-miss-why">{(one.broke ?? []).map((broke) => `${broke.check}: ${broke.detail}`).join(" · ")}</div>
                  </div>
                ))}
            </>
          )}
        </Card>
      </div>
      <Refused>{refused}</Refused>
    </>
  );
}

function Figure({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div style={{ minWidth: 0 }}>
      <div className="mem-figure-label">{label}</div>
      <div className="mem-figure ui-clip">{value}</div>
    </div>
  );
}

function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : failed instanceof Error ? failed.message : String(failed);
}
