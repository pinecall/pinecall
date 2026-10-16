/** Docs screen: the agent's knowledge bases, each opening onto its files, and dropping one. */

import { type KnowledgeBase } from "@pinecall/core/wire/rest-retrieval";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Empty, Page, PageHead, Pill, Refused, TableHead, TableRow, TextAction } from "../../ui";
import { useAttached } from "./attached";
import { dropBase, readBases } from "./door";
import "./docs.css";

const COLUMNS = "minmax(0,1fr) 150px 90px 150px 80px";

/** List and drop go to the gateway; a project pushes its folder with `pinecall docs push`. */
export function Docs(): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const [bases, setBases] = useState<KnowledgeBase[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const attached = useAttached(agent);

  const reread = useCallback(async (): Promise<void> => {
    setBases((await readBases(credentials)).bases);
  }, [credentials]);

  useEffect(() => {
    let gone = false;
    reread().catch((failed: unknown) => {
      if (!gone) setRefused(saidBy(failed));
    });
    return () => {
      gone = true;
    };
  }, [credentials, agent, reread]);

  const forget = async (name: string): Promise<void> => {
    if (!window.confirm(`Delete the base ${name}? It cannot be undone; pushing the folder again recreates it.`)) return;
    setRefused(null);
    try {
      await dropBase(credentials, name);
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Page width={1060} tight>
      <PageHead
        title="Docs"
        ledeWidth={620}
        lede="Documents this agent can search while it talks. Open a base to read and edit its files. Which bases this agent reads is chosen in Configure."
      />

      <Refused>{refused ?? attached.refused}</Refused>

      <Card>
        <CardHead title="Knowledge bases" meta={`${(bases ?? []).length} in this org`} action={<Link to={`/a/${encodeURIComponent(agent)}/configure`}>Choose which this agent reads</Link>} />
        {bases !== null && bases.length === 0 ? (
          <Empty>No knowledge base yet. Push a folder from your project with `pinecall docs push`.</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["Base", "This agent", "Chunks", "Updated", ""]} />
            {(bases ?? []).map((one) => {
              const how = attached.read?.get(one.base);
              return (
                <TableRow key={one.base} columns={COLUMNS} to={`/docs/${encodeURIComponent(one.base)}`}>
                  <span className="ui-cell-strong ui-clip" title={`embedded with ${one.model}`}>
                    {one.base}
                  </span>
                  <span title={how === undefined ? undefined : `${how.mode ?? "retrieved"}, up to ${how.k ?? 8} chunks a turn`}>
                    {attached.read === null ? null : how === undefined ? <Pill tone="gray">not read</Pill> : <Pill tone="green">reads it</Pill>}
                  </span>
                  <span className="ui-cell-ink">{one.chunks}</span>
                  <span className="ui-cell">{dayAndTime(one.pushed_at)}</span>
                  <span className="ui-cell-end">
                    <TextAction danger onClick={() => void forget(one.base)}>
                      Delete
                    </TextAction>
                  </span>
                </TableRow>
              );
            })}
          </>
        )}
      </Card>
    </Page>
  );
}

function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : failed instanceof Error ? failed.message : String(failed);
}
