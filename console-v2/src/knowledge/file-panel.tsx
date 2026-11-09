/** One file of a base in the side panel: read as the page it is, edited one click away; a new one starts with its path and an empty page. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { KnowledgeFileRead } from "@pinecall/core/wire/rest-retrieval";
import { ago, count } from "../lib/format";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { chunksIn, putFile, readFile } from "./door";
import { Markdown } from "./markdown";

// It docks beside the page, so what it takes the page loses.
const WIDTH = 540;

/** `path` null is a file not written yet; `taken` are the paths it may not use. */
export function FilePanel({ base, path, taken, onClose, onKept }: { base: string; path: string | null; taken: readonly string[]; onClose: () => void; onKept: (said: string, isNew: boolean) => void }): ReactNode {
  const credentials = useCredentials();
  const isNew = path === null;
  const [name, setName] = useState("");
  const [held, setHeld] = useState<KnowledgeFileRead | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(isNew);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    if (path === null) return;
    let gone = false;
    readFile(credentials, base, path).then(
      (read) => {
        if (gone) return;
        setHeld(read);
        setText(read.text);
      },
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, base, path]);

  const named = name.trim();
  const clash = isNew && taken.includes(named);
  const changed = isNew ? named !== "" && text.trim() !== "" : held !== null && text !== held.text;

  const save = async (): Promise<void> => {
    setBusy(true);
    setSaid(null);
    setRefused(null);
    try {
      const pushed = await putFile(credentials, base, isNew ? named : path, text);
      const line = `${pushed.path} saved, ${chunksIn(pushed.chunks)}`;
      if (!isNew && held !== null) setHeld({ ...held, text, chunks: pushed.chunks, pushed_at: Date.now() / 1000 });
      setSaid(`Saved, ${chunksIn(pushed.chunks)}. Searchable on the next call.`);
      onKept(line, isNew);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const switcher = isNew ? undefined : (
    <div className="dash-switch" role="group" aria-label="How the file is shown">
      <button type="button" aria-pressed={!editing} className={editing ? "" : "dash-switch-on"} onClick={() => setEditing(false)}>
        Read
      </button>
      <button type="button" aria-pressed={editing} className={editing ? "dash-switch-on" : ""} disabled={held === null} onClick={() => setEditing(true)}>
        Edit
      </button>
    </div>
  );

  const failedLine = refused !== null && (
    <p className="cfg-refused" role="alert">
      {refused}
    </p>
  );

  const footer = editing ? (
    <>
      {failedLine}
      <div className="kb-panel-foot">
        <span className="dash-quiet" role="status">
          {said ?? (changed ? "Not saved yet." : "Markdown works best: a search finds a passage by its headings.")}
        </span>
        <button type="button" className="cfg-save" disabled={busy || !changed || clash} onClick={() => void save()}>
          {busy ? "Saving…" : isNew ? "Add to the base" : "Save"}
        </button>
      </div>
    </>
  ) : refused !== null ? (
    failedLine
  ) : undefined;

  const about = isNew ? "It is searchable on the next call, and only this file is cut." : held === null ? undefined : `${count(text.length)} characters, ${chunksIn(held.chunks)}, updated ${ago(held.pushed_at)}.`;

  return (
    <SidePanel title={path ?? "A new file"} icon="knowledge" about={about} actions={switcher} footer={footer} width={WIDTH} onClose={onClose}>
      {isNew && (
        <Field label="Path in the base">
          <input className="cfg-input" autoFocus spellCheck={false} placeholder="faq/hours.md" value={name} disabled={busy} onChange={(event) => setName(event.target.value)} />
          {clash && <span className="cfg-refused">There is a file at that path already. Open it to change it.</span>}
        </Field>
      )}
      {!isNew && held === null && refused === null && <p className="dash-quiet">Reading the file…</p>}
      {editing ? (
        <textarea className="cfg-input cfg-area kb-text" spellCheck={false} aria-label={path ?? "The new file"} placeholder={"# Hours\n\nMonday to Friday, 9 to 18."} value={text} disabled={busy} onChange={(event) => setText(event.target.value)} />
      ) : (
        held !== null && <Markdown text={text} />
      )}
    </SidePanel>
  );
}
