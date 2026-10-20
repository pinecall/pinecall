/** Needs a look: the newest calls a reviewer should open first, and every agent whose newest suite has goldens that broke — each one click from where it is fixed. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { whoOn } from "@pinecall/core/calls";
import { dayOf, webVisitor } from "../../lib/format";
import { Card, CardAction, CardHead, Icon, Pill, type IconName } from "../../ui";
import type { Suite } from "../evals";
import { worthALook } from "./counted";

/** What kind of thing it is, and how the row draws it: its icon, its tint, and the words beside the name. */
type Kind = "golden" | "low_score" | "escalated" | "promise";

const KINDS: Record<Kind, { icon: IconName; tint: "indigo" | "red" | "amber"; said: string }> = {
  golden: { icon: "flask", tint: "indigo", said: "Test" },
  low_score: { icon: "scale", tint: "red", said: "A judge said no" },
  escalated: { icon: "persona", tint: "amber", said: "A person took part" },
  promise: { icon: "words", tint: "amber", said: "A promise no tool recorded" },
};

/** One thing to look at: what it is, whose and when, why, and where it is fixed. */
interface Look {
  key: string;
  kind: Kind;
  title: string;
  where: string;
  why: string;
  to: string;
  go: string;
}

function looksAt(lines: readonly SessionLine[], suites: readonly Suite[], agent: string): Look[] {
  const calls = worthALook(lines).map(
    (line): Look => ({
      key: line.call,
      kind: line.flags?.[0] ?? "escalated",
      title: whoOn(line, webVisitor),
      where: `${line.agent} · ${dayOf(line.started_at)}`,
      why: line.score?.reason ?? line.outcome ?? "—",
      to: agent === "" ? `/calls/${line.call}` : `/a/${encodeURIComponent(agent)}/calls/${line.call}`,
      go: "Open the call",
    }),
  );
  const goldens = suites
    .filter((suite) => suite.failing.length > 0)
    .map(
      (suite): Look => ({
        key: `suite:${suite.agent}`,
        kind: "golden",
        title: `${suite.failing.length} ${suite.failing.length === 1 ? "golden" : "goldens"} broke`,
        where: `${suite.agent} · newest run`,
        why: `${suite.held} of ${suite.cells} held: ${suite.failing.slice(0, 2).join(", ")}${suite.failing.length > 2 ? "…" : ""}`,
        to: `/a/${encodeURIComponent(suite.agent)}/goldens`,
        go: "Open Test",
      }),
    );
  return [...goldens, ...calls];
}

export function NeedsALook({ lines, suites, agent }: { lines: readonly SessionLine[]; suites: readonly Suite[]; agent: string }): ReactNode {
  const looks = looksAt(lines, suites, agent);
  return (
    <Card>
      <CardHead
        title="Needs a look"
        meta={
          looks.length === 0 ? undefined : (
            <Pill tone="amber" small>
              {looks.length} open
            </Pill>
          )
        }
        action={<CardAction to={agent === "" ? "/cases" : `/a/${encodeURIComponent(agent)}/cases`}>See all in Cases</CardAction>}
      />
      {looks.length === 0 ? (
        <p className="ovw-quiet ovw-quiet-card">Nothing needs a look: no call went to a person or broke a judge, and every golden held.</p>
      ) : (
        <div className="ovw-looks">
          {looks.map((look) => {
            const kind = KINDS[look.kind];
            return (
              <Link key={look.key} to={look.to} className="ovw-look">
                <span className={`ovw-look-icon ui-tint-${kind.tint}`} aria-hidden>
                  <Icon name={kind.icon} size={17} />
                </span>
                <span className="ovw-look-words">
                  <span className="ovw-look-top">
                    <span className="ovw-look-title">{look.title}</span>
                    <span className={`ovw-look-kind ovw-look-kind-${kind.tint}`}>{kind.said}</span>
                    <span className="ovw-look-where">{look.where}</span>
                  </span>
                  <span className="ovw-look-why">{look.why}</span>
                </span>
                <span className="ovw-look-go">{look.go} →</span>
              </Link>
            );
          })}
        </div>
      )}
    </Card>
  );
}
