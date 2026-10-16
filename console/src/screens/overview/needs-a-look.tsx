/** Needs a look: the newest calls a reviewer should open first, and every agent whose newest suite has goldens that broke — each one click from where it is fixed. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { whoOn } from "@pinecall/core/calls";
import { ago, webVisitor } from "../../lib/format";
import { Card, CardHead } from "../../ui";
import type { Suite } from "../evals";
import { worthALook } from "./counted";

// What each flag the gateway raises on a call means to the person reading the list.
const FLAG_SAID = { escalated: "A person took part", low_score: "A judge said no", promise: "A promise no tool recorded" } as const;

/** One thing to look at: how bad, what it is, why, and where it is fixed. */
interface Look {
  key: string;
  severe: boolean;
  title: string;
  why: string;
  when: string;
  to: string;
  go: string;
}

function looksAt(lines: readonly SessionLine[], suites: readonly Suite[], agent: string): Look[] {
  const calls = worthALook(lines).map((line): Look => {
    const flag = line.flags?.[0] ?? "escalated";
    return {
      key: line.call,
      severe: flag === "low_score",
      title: `${whoOn(line, webVisitor)} · ${FLAG_SAID[flag]}`,
      why: line.score?.reason ?? line.outcome ?? "—",
      when: ago(line.started_at),
      to: agent === "" ? `/calls/${line.call}` : `/a/${encodeURIComponent(agent)}/calls/${line.call}`,
      go: "Open the call",
    };
  });
  const goldens = suites
    .filter((suite) => suite.failing.length > 0)
    .map(
      (suite): Look => ({
        key: `suite:${suite.agent}`,
        severe: true,
        title: `${suite.failing.length} ${suite.failing.length === 1 ? "golden" : "goldens"} broke${agent === "" ? ` · ${suite.agent}` : ""}`,
        why: `${suite.held} of ${suite.cells} held in the newest run: ${suite.failing.slice(0, 2).join(", ")}${suite.failing.length > 2 ? "…" : ""}`,
        when: ago(suite.at),
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
      <CardHead title="Needs a look" meta={looks.length === 0 ? undefined : `${looks.length} open`} />
      {looks.length === 0 ? (
        <p className="ovw-quiet ovw-quiet-card">Nothing needs a look: no call went to a person or broke a judge, and every golden held.</p>
      ) : (
        <div className="ovw-looks">
          {looks.map((look) => (
            <Link key={look.key} to={look.to} className="ovw-look">
              <span className={look.severe ? "ovw-look-mark ovw-look-mark-severe" : "ovw-look-mark"} aria-hidden />
              <span className="ovw-look-words">
                <span className="ovw-look-title">{look.title}</span>
                <span className="ovw-look-why">{look.why}</span>
              </span>
              <span className="ovw-look-end">
                <span className="ovw-look-go">{look.go} →</span>
                <span className="ovw-look-when">{look.when}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}
