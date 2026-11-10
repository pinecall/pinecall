/** What every agent carries from one call to the next with the same caller, newest first, forgotten one row at a time. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { prettyNumber } from "@pinecall/core/calls";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { AgentLink } from "./agent-link";
import { forgetFact, readFacts, type Fact } from "./door";

const SEARCH_WAITS_MS = 300;

const callerOf = (contact: string): string => (contact.startsWith("+") ? prettyNumber(contact) : contact);

export function MemoryView(): ReactNode {
  const credentials = useCredentials();
  const [words, setWords] = useState("");
  const [asked, setAsked] = useState("");
  // undefined while asking, null when this gateway keeps no memory.
  const [facts, setFacts] = useState<Fact[] | null | undefined>(undefined);
  const [next, setNext] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    const waiting = window.setTimeout(() => setAsked(words.trim()), SEARCH_WAITS_MS);
    return () => window.clearTimeout(waiting);
  }, [words]);

  useEffect(() => {
    let gone = false;
    setRefused(null);
    readFacts(credentials, asked, null).then(
      (page) => {
        if (gone) return;
        setFacts(page === null ? null : page.facts);
        setNext(page?.next ?? null);
      },
      (failed: unknown) => {
        if (gone) return;
        setFacts((was) => was ?? []);
        setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, asked]);

  const more = async (): Promise<void> => {
    if (next === null) return;
    try {
      const page = await readFacts(credentials, asked, next);
      if (page === null) return;
      setFacts((shown) => [...(shown ?? []), ...page.facts]);
      setNext(page.next ?? null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const forget = async (fact: Fact): Promise<void> => {
    setRefused(null);
    try {
      await forgetFact(credentials, fact.id);
      setFacts((shown) => (shown ?? []).filter((one) => one.id !== fact.id));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <div className="kb-page">
      <section className="dash-card" aria-label="What the agents remember">
        <div className="kb-bar">
          <span className="dash-eyebrow">Remembered</span>
          <span className="kb-said" />
          {facts !== null && <input className="app-input kb-look" aria-label="Search what is remembered" placeholder="Search a caller, a word" value={words} onChange={(event) => setWords(event.target.value)} />}
        </div>
        {refused !== null && (
          <p className="cfg-refused kb-refused" role="alert">
            {refused}
          </p>
        )}
        {facts === undefined ? (
          <p className="dash-quiet">Reading what the agents remember…</p>
        ) : facts === null ? (
          <p className="dash-quiet">This gateway keeps no memory: it runs without the database memory lives in.</p>
        ) : facts.length === 0 ? (
          <p className="dash-quiet">{asked === "" ? "No agent remembers anything yet. An agent with memory rules writes what it learned when a call hangs up." : "Nothing remembered matches."}</p>
        ) : (
          <>
            <div className="kb-rows">
              {facts.map((fact) => (
                <div key={fact.id} className="kb-row dash-row">
                  <div className="kb-row-main">
                    <span className="kb-fact">
                      {fact.text}
                      {fact.category !== null && fact.category !== undefined && fact.category !== "" && <span className="dash-tag">{fact.category}</span>}
                    </span>
                    <span className="kb-row-under kb-fact-who">
                      <span className="dash-clip" title={fact.contact}>
                        {callerOf(fact.contact)}
                      </span>
                      <span aria-hidden="true">·</span>
                      <AgentLink name={fact.agent} className="dash-clip kb-fact-agent" />
                    </span>
                  </div>
                  <span className="kb-row-date">{ago(fact.written_at)}</span>
                  <span className="kb-row-end">
                    <ConfirmButton label="Forget" asks="Forget it?" danger onConfirm={() => void forget(fact)} />
                  </span>
                </div>
              ))}
            </div>
            {next !== null && (
              <button type="button" className="app-button kb-more" onClick={() => void more()}>
                Load more
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
