/** Org Docs screen: every base in this world, its size, embedder and reader agents. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { Button, Card, Empty, Page, PageHead, Refused, TableHead, TableRow } from "../../ui";
import "./org-docs.css";
import { readBasesRead, type BaseRead } from "./door";
import { NewBase } from "./new-base";

const COLUMNS = "minmax(0,1fr) 90px 140px 150px minmax(0,1fr)";

function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

// Readers come from each agent's latest settings; attaching a base is done in Settings.
export function OrgDocs(): ReactNode {
  const credentials = useCredentials();
  const [bases, setBases] = useState<BaseRead[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let gone = false;
    readBasesRead(credentials).then(
      (read) => {
        if (!gone) setBases(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return (
    <Page width={1060} tight>
      <PageHead
        title="Docs"
        ledeWidth={640}
        lede="Every base of documents in this world, and which agents search it. Create one here, or push a whole folder from a project with `pinecall docs push`; open a base to read, add, edit or take out its files, and attach it to an agent in its Settings."
        actions={
          !adding && (
            <Button kind="primary" size="form" onClick={() => setAdding(true)}>
              New base
            </Button>
          )
        }
      />

      {adding && <NewBase taken={(bases ?? []).map((one) => one.base)} onCancel={() => setAdding(false)} />}

      <Refused>{refused}</Refused>

      <Card>
        {bases === null ? (
          <Empty>{refused === null ? "Asking the gateway…" : "The bases could not be read."}</Empty>
        ) : bases.length === 0 ? (
          <Empty>No base yet. Create one with New base, or push a folder from a project with `pinecall docs push`.</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["Base", "Chunks", "Embedder", "Pushed", "Read by"]} />
            {bases.map((one) => (
              <TableRow key={one.base} columns={COLUMNS} to={`/docs/${encodeURIComponent(one.base)}`}>
                <span className="ui-cell-strong ui-clip">{one.base}</span>
                <span className="ui-cell-ink">{one.chunks}</span>
                <span className="ui-cell ui-clip">{one.model}</span>
                <span className="ui-cell">{dayAndTime(one.pushed_at)}</span>
                <span className="ui-cell ui-clip">
                  {one.agents.length === 0
                    ? "nobody"
                    : one.agents.map((agent, at) => (
                        <span key={agent}>
                          {at > 0 && ", "}
                          <Link to={`/a/${encodeURIComponent(agent)}/configure`}>{agent}</Link>
                        </span>
                      ))}
                </span>
              </TableRow>
            ))}
          </>
        )}
      </Card>
    </Page>
  );
}
