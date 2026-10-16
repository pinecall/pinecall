/** Org Memory screen: every agent's stored facts, each with its agent. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { dayOf } from "../../lib/format";
import { Button, Card, CardHead, Empty, Input, Page, PageHead, Refused, TableHead, TextAction } from "../../ui";
import { dropFact } from "../memory/door";
import { readOrgMemory, type OrgFact } from "./door";
import "../memory/memory.css";

const COLUMNS = "150px 140px minmax(0,1fr) 100px 64px";

function callerOf(contact: string): string {
  return contact.startsWith("+") ? prettyNumber(contact) : contact;
}

function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

export function OrgMemory(): ReactNode {
  const credentials = useCredentials();
  const [words, setWords] = useState("");
  const [asked, setAsked] = useState("");
  const [facts, setFacts] = useState<OrgFact[] | null | undefined>(undefined);
  const [next, setNext] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  // Debounced server-side search: `q` matches text, caller and category across all pages.
  useEffect(() => {
    const waiting = window.setTimeout(() => setAsked(words.trim()), 300);
    return () => window.clearTimeout(waiting);
  }, [words]);

  useEffect(() => {
    let gone = false;
    setRefused(null);
    readOrgMemory(credentials, asked, null).then(
      (page) => {
        if (gone) return;
        setFacts(page === null ? null : page.facts);
        setNext(page?.next ?? null);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, asked]);

  const more = async (): Promise<void> => {
    if (next === null) return;
    try {
      const page = await readOrgMemory(credentials, asked, next);
      if (page === null) return;
      setFacts((shown) => [...(shown ?? []), ...page.facts]);
      setNext(page.next ?? null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const drop = async (fact: OrgFact): Promise<void> => {
    if (!window.confirm(`Drop "${fact.text}"? The rest of what memory keeps about ${callerOf(fact.contact)} stays.`)) return;
    setRefused(null);
    try {
      await dropFact(credentials, fact.id);
      setFacts((shown) => (shown ?? []).filter((one) => one.id !== fact.id));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Page width={1060} tight>
      <PageHead
        title="Memory"
        ledeWidth={640}
        lede="What every agent carries between calls with the same caller — newest first, each fact with the agent whose call taught it, droppable one row at a time."
      />

      <Card>
        <CardHead title="Remembered" meta={facts ? `${facts.length}${next !== null ? "+" : ""} facts` : undefined}>
          <div className="mem-look">
            <Input size="sm" value={words} placeholder="Search a caller, a word, a category" onChange={(event) => setWords(event.target.value)} />
          </div>
        </CardHead>

        {facts === undefined ? (
          <Empty>Asking the gateway what the agents remember…</Empty>
        ) : facts === null ? (
          <Empty>This gateway keeps no memory: it runs without the database memory lives in.</Empty>
        ) : facts.length === 0 ? (
          <Empty>{asked === "" ? "No agent remembers anything about any caller yet. An agent that declares `memory` writes what it learns when a call hangs up." : "Nothing remembered matches."}</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["Caller", "Agent", "Remembered", "Written", "Action>"]} />
            {facts.map((fact) => (
              <div key={fact.id} className="ui-table-row" style={{ gridTemplateColumns: COLUMNS }}>
                <span className="mem-caller ui-clip" title={fact.contact}>
                  {callerOf(fact.contact)}
                </span>
                <span className="ui-clip">
                  <Link to={`/a/${encodeURIComponent(fact.agent)}/memory`}>{fact.agent}</Link>
                </span>
                <span className="mem-fact">
                  {fact.text}
                  {fact.category ? <span className="mem-superseded"> · {fact.category}</span> : null}
                </span>
                <span className="ui-cell-faint">{dayOf(fact.written_at)}</span>
                <span className="ui-cell-end">
                  <TextAction danger onClick={() => void drop(fact)}>
                    Drop
                  </TextAction>
                </span>
              </div>
            ))}
            {next !== null && (
              <div className="ui-card-foot">
                <Button size="sm" onClick={() => void more()}>
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </Card>

      <Refused>{refused}</Refused>
    </Page>
  );
}
