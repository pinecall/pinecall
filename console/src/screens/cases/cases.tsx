/** Cases: what a judge broke on, as one list of groups — a cause each, the one move that fits it — then what a person kept or wrote; a case open is the whole screen. */

import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { rowAt } from "../../lib/harness";
import { Button, Chips, Empty, Page, PageHead } from "../../ui";
import { CaseList } from "./case-list";
import { CaseView } from "./case-view";
import type { CaseGroup } from "./door";
import { GroupRow } from "./group-row";
import { NewCase } from "./new-case";
import { useCases } from "./use-cases";
import "./cases.css";

type Show = CaseGroup["status"];

const SHOWS: readonly Show[] = ["pending", "approved", "dismissed"];

const LABEL = { pending: "Waiting", approved: "Played nightly", dismissed: "Dismissed" } as const;

/**
 * One screen whoever is in view. A case is the org's — kept by the gateway, the same in both
 * worlds — and the URL names the one open: `/a/<agent>/cases/<name>`, or `/cases/<agent>/<name>`
 * with every agent in view. What this page decides is what `pinecall cases` and the nightly's
 * `pinecall test --dataset` read, with no deploy between.
 */
export function Cases(): ReactNode {
  const params = useParams();
  const agent = params["agent"] ?? "";
  const owner = params["owner"] ?? agent;
  const open = params["call"];
  const [show, setShow] = useState<Show>("pending");
  const [writing, setWriting] = useState(false);
  const { listed, groups, asking, decided, grouped, written } = useCases(agent);
  const chosen = listed?.cases.find((kept) => kept.agent === owner && kept.name === open);

  if (chosen !== undefined) {
    return (
      <div className="cs-open">
        <Link className="cs-back" to={rowAt(agent, "cases")}>
          ← Cases
        </Link>
        <CaseView key={chosen.id} agent={chosen.agent} kept={chosen} onDecided={decided} />
      </div>
    );
  }
  const counted = (status: Show): number => (groups ?? []).filter((group) => group.status === status).length;
  const these = (groups ?? []).filter((group) => group.status === show);
  // A case a person kept from a call, or wrote here, joins no judge's group.
  const byHand = (listed?.cases ?? []).filter((kept) => (kept.group ?? null) === null && kept.status === show);
  return (
    <Page width={900}>
      <PageHead
        title="Cases"
        lede="Real calls a judge broke on, grouped by cause, and the cases a person kept or wrote."
        actions={agent !== "" && !writing && <Button onClick={() => setWriting(true)}>New case</Button>}
      />
      {writing && (
        <NewCase
          agent={agent}
          onClose={() => setWriting(false)}
          onWritten={(kept) => {
            written(kept);
            setWriting(false);
            setShow(kept.status);
          }}
        />
      )}
      <Chips options={SHOWS.map((status) => ({ value: status, label: `${LABEL[status]} ${groups === null ? "" : String(counted(status))}`.trim() }))} value={show} onChange={setShow} />
      {groups === null && <p className="cs-empty">{asking ?? "Asking the gateway…"}</p>}
      {groups !== null && these.length === 0 && byHand.length === 0 && (
        <Empty>{show === "pending" ? "Nothing waits for you." : `Nothing is ${LABEL[show].toLowerCase()}.`}</Empty>
      )}
      {these.length > 0 && (
        <ul className="cs-groups">
          {these.map((group) => (
            <GroupRow key={group.id} agent={agent} group={group} calls={(listed?.cases ?? []).filter((kept) => kept.group === group.id)} onGrouped={grouped} />
          ))}
        </ul>
      )}
      {byHand.length > 0 && (
        <>
          <h2 className="cs-by-hand-title">Kept by a person</h2>
          <CaseList agent={agent} cases={byHand} />
        </>
      )}
      {listed !== null && listed.pending >= listed.pendingAtMost && (
        <p className="cs-bad">The inbox is full: a call that breaks now is judged as ever and not kept, until you decide some of these.</p>
      )}
    </Page>
  );
}
