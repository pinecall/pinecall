/** Finished-call log view: one row per entry, turn metrics expandable under each turn. */

import { type Turn } from "@pinecall/core/wire/state";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router";

import { headline } from "@pinecall/core/metrics";
import { Button, Card, CardHead } from "../../../ui";
import type { Line } from "./transcript";

// Entries and reducer turns join on the utterance id per role. Chips come from the reducer turn
// (@pinecall/core/metrics); expanded field lines are the entry's raw values.
const ROLES: Record<string, string> = { "turn.user": "user", "turn.agent": "agent" };

// `#seq-N` links to a row (a verdict's evidence). The log loads after the browser handles
// the fragment, so we scroll manually once rows render.
const AT_SEQ = /^#seq-(\d+)$/;

export function Timeline({ lines, turns }: { lines: Line[]; turns: Turn[] }): ReactNode {
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const [all, setAll] = useState(false);
  const spoken = byUtterance(turns);
  const cited = seqNamedBy(useLocation().hash);
  const drawn = lines.length;

  useEffect(() => {
    if (cited !== null && drawn > 0) {
      document.getElementById(anchorOf(cited))?.scrollIntoView({ block: "center" });
    }
  }, [cited, drawn]);

  const toggle = (seq: number): void =>
    setOpened((held) => {
      const next = new Set(held);
      if (!next.delete(seq)) {
        next.add(seq);
      }
      return next;
    });

  return (
    <Card>
      <CardHead
        title="The log"
        meta={`${lines.length} entries, append-only, numbered by seq`}
        action={
          <span className="over-log-action">
            <Button size="sm" onClick={() => setAll(!all)}>
              {all ? "Hide the fields" : "Show every field"}
            </Button>
          </span>
        }
      />
      <div className="over-log">
        {lines.map((line) => (
          <Row
            key={line.entry.seq}
            line={line}
            turn={spoken.get(keyOf(line.entry.type, line.entry.data))}
            open={all || opened.has(line.entry.seq)}
            cited={line.entry.seq === cited}
            onToggle={() => toggle(line.entry.seq)}
          />
        ))}
      </div>
    </Card>
  );
}

/** Parse `#seq-N` from a URL hash, or null. */
function seqNamedBy(hash: string): number | null {
  const digits = AT_SEQ.exec(hash)?.[1];
  return digits === undefined ? null : Number(digits);
}

/** DOM id of a log row, matching the `#seq-N` fragment. */
function anchorOf(seq: number): string {
  return `seq-${seq}`;
}

function Row({
  line,
  turn,
  open,
  cited,
  onToggle,
}: {
  line: Line;
  turn: Turn | undefined;
  open: boolean;
  cited: boolean;
  onToggle: () => void;
}): ReactNode {
  const fields = line.fields.length > 0;
  const classes = ["over-entry", `over-entry-${familyOf(line.entry.type)}`];
  if (fields) classes.push("over-entry-opens");
  if (cited) classes.push("over-entry-cited");
  return (
    <div id={anchorOf(line.entry.seq)} className={classes.join(" ")} onClick={fields ? onToggle : undefined}>
      <span className="over-entry-seq">{line.entry.seq}</span>
      <span className="over-entry-since">{line.since}</span>
      <span className="over-entry-type">
        {line.mark !== "" && <span className="over-entry-mark">{line.mark} </span>}
        {line.entry.type}
      </span>
      <span className="over-entry-payload">
        {line.payload}
        {fields && <span className="over-entry-caret"> {open ? "▾" : "▸"}</span>}
        {turn !== undefined && <Chips turn={turn} />}
        {open && (
          <span className="over-fields">
            {line.fields.map((field) => (
              <span key={field.name} className="over-field">
                <span className="over-field-name">{field.name}</span>
                <span className="over-field-value">{field.value}</span>
              </span>
            ))}
          </span>
        )}
      </span>
    </div>
  );
}

function familyOf(type: string): string {
  if (type.startsWith("turn.")) return "turn";
  if (type.startsWith("state.")) return "state";
  if (type.startsWith("tool.") || type.startsWith("confirm.")) return "tool";
  if (type.startsWith("call.")) return "call";
  return "quiet";
}

function Chips({ turn }: { turn: Turn }): ReactNode {
  return (
    <span className="over-chips">
      {headline(turn).map((reading) => (
        <span key={reading.field} className="over-chip">
          {reading.field} <b>{reading.value}</b>
        </span>
      ))}
    </span>
  );
}

// Key by `item_id`, not `speech_id`: one reply (one speech_id) can hold several `turn.agent`
// utterances, and keying by reply would show the last one's text on every row.
function byUtterance(turns: Turn[]): Map<string, Turn> {
  return new Map(turns.map((turn) => [keyFor(turn.role, turn.item_id, turn.speech_id), turn]));
}

function keyOf(type: string, data: Record<string, unknown>): string {
  return keyFor(ROLES[type] ?? "", data["item_id"], data["speech_id"]);
}

// `item_id` may be absent; then the turn is its reply's only utterance and `speech_id` suffices.
function keyFor(role: string, item: unknown, speech: unknown): string {
  const said = typeof item === "string" && item !== "" ? item : speech;
  return `${role}:${typeof said === "string" ? said : ""}`;
}
