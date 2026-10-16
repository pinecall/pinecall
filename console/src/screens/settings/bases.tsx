/** The bases the agent searches per turn, picked from the ones this org has pushed: the Bases section. */

import type { ReactNode } from "react";

import { type KnowledgeBase } from "@pinecall/core/wire/rest-retrieval";

import { Button, Label, Select, SelectItem } from "../../ui";
import type { Attachment } from "./typed";

const ATTACH = "";

// How many chunks a turn may read, as a list: at least one (types/knowledge.py), and the runtime
// hands the model eight when nobody said.
const CHUNKS = ["2", "4", "6", "8", "12", "16"];

// The floor a chunk of THIS base must reach, on the 0..1 scale the fusion normalises to. It is
// read against the best chunk of the turn, so 0.5 cuts the tail and 0.02 cuts nothing at all —
// and no value of it can say "nothing here answers this" (runtime/docs/retrieval/spec.md).
const FLOORS = ["0.2", "0.3", "0.4", "0.5", "0.6", "0.7"];

/** One row of a Select's own values plus whatever the corner already holds, so nothing is lost by opening the form. */
function withWhatIsSet(value: string, offered: readonly string[]): readonly string[] {
  return value === "" || offered.includes(value) ? offered : [value, ...offered];
}

export function BasesSection({ rows, offered, onChange }: { rows: readonly Attachment[]; offered: readonly KnowledgeBase[] | null; onChange: (rows: Attachment[]) => void }): ReactNode {
  const attached = new Set(rows.map((one) => one.base));
  const free = (offered ?? []).filter((one) => !attached.has(one.base));
  const set = (at: number, row: Attachment): void => onChange(rows.map((one, index) => (index === at ? row : one)));
  const drop = (at: number): void => onChange(rows.filter((_, index) => index !== at));
  return (
    <section className="set-section">
      <div className="set-section-head">
        <h2 className="set-section-title">Bases</h2>
        <p className="set-section-blurb">The documents the agent searches on every turn, by the name each folder was pushed under. A base is pushed from a project with `pinecall docs push`; the Docs tab lists them.</p>
      </div>
      {rows.length === 0 ? (
        <p className="set-help">Nothing attached: the agent answers from what it knows by heart and from its tools alone. Attach one below, and every turn searches it before the model speaks.</p>
      ) : (
        <div className="set-bases">
          <div className="set-bases-head">
            <span>Base</span>
            <span>Chunks a turn reads</span>
            <span>Searched by</span>
            <span>Least score kept</span>
            <span />
          </div>
          {rows.map((row, at) => (
            <div className="set-bases-row" key={`${row.base}-${at}`}>
              <Select value={row.base} aria-label="Base" onValueChange={(value) => set(at, { ...row, base: value })}>
                {(offered ?? []).some((one) => one.base === row.base) ? null : <SelectItem value={row.base}>{row.base} · not pushed in this world</SelectItem>}
                {(offered ?? []).map((one) => (
                  <SelectItem key={one.base} value={one.base} disabled={one.base !== row.base && attached.has(one.base)}>
                    {one.base} · {one.chunks} chunks
                  </SelectItem>
                ))}
              </Select>
              <Select value={row.k} aria-label="Chunks a turn reads" onValueChange={(value) => set(at, { ...row, k: value })}>
                <SelectItem value="">Runtime default · 8</SelectItem>
                {withWhatIsSet(row.k, CHUNKS).map((k) => (
                  <SelectItem key={k} value={k}>
                    {k}
                  </SelectItem>
                ))}
              </Select>
              <Select value={row.mode} aria-label="Searched by" onValueChange={(value) => set(at, { ...row, mode: value === "tool" ? "tool" : "retrieved" })}>
                <SelectItem value="retrieved">The platform, before every turn</SelectItem>
                <SelectItem value="tool">The model, when it decides</SelectItem>
              </Select>
              <Select value={row.min_score} aria-label="Least score kept" onValueChange={(value) => set(at, { ...row, min_score: value })}>
                <SelectItem value="">Keep them all</SelectItem>
                {withWhatIsSet(row.min_score, FLOORS).map((floor) => (
                  <SelectItem key={floor} value={floor}>
                    {floor}
                  </SelectItem>
                ))}
              </Select>
              <Button size="xs" onClick={() => drop(at)}>
                Detach
              </Button>
            </div>
          ))}
        </div>
      )}
      {rows.length > 1 && (
        <p className="set-help">
          Several bases are one search, not several: they are read together and ranked against each other, so a collection with nothing to say about the question takes none of the turn&apos;s chunks. The turn is handed the most generous <strong>chunks a turn reads</strong> of the rows above, and each <strong>least score kept</strong> is read against the base that set it.
        </p>
      )}
      <div className="set-row">
        <div className="set-field">
          <Label>Attach a base</Label>
          <Select value={ATTACH} aria-label="Attach a base" disabled={free.length === 0} onValueChange={(value) => value !== ATTACH && onChange([...rows, { base: value, k: "", mode: "retrieved", min_score: "" }])}>
            <SelectItem value={ATTACH}>{offered === null ? "Asking the gateway…" : free.length === 0 ? "Every pushed base is attached" : "Pick one…"}</SelectItem>
            {free.map((one) => (
              <SelectItem key={one.base} value={one.base}>
                {one.base} · {one.chunks} chunks
              </SelectItem>
            ))}
          </Select>
          <p className="set-help">Only bases pushed in this world appear. A base a colleague pushed to their own corner is theirs until they push it for the team.</p>
        </div>
      </div>
    </section>
  );
}
