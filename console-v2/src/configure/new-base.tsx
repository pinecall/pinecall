/** A new knowledge base, made where it is used: a name and its first documents, sent one file at a time. */

import { useState, type ChangeEvent, type DragEvent, type ReactNode } from "react";

import { put, saidBy, type Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { KnowledgeFilePushedSchema } from "@pinecall/core/wire/rest-retrieval";

// The rule of `pinecall docs push --base`.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const A_DOCUMENT = /\.(md|markdown|txt)$/i;

async function putFile(credentials: Credentials, base: string, path: string, text: string): Promise<void> {
  KnowledgeFilePushedSchema.parse(await put(credentials, `/v1/knowledge/${encodeURIComponent(base)}/files/${encodeURIComponent(path)}`, { text }));
}

export function NewBase({ taken, using, onMade, onCancel }: { taken: readonly string[]; using: boolean; onMade: (name: string) => void; onCancel: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<readonly File[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [over, setOver] = useState(false);
  const [sent, setSent] = useState<number | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const nameBad = name !== "" && !A_NAME.test(name);
  const clash = taken.includes(name);
  const busy = sent !== null;
  const ready = A_NAME.test(name) && !clash && files.length > 0 && !busy;

  const take = (picked: readonly File[]): void => {
    const documents = picked.filter((one) => A_DOCUMENT.test(one.name));
    setSkipped(picked.length - documents.length);
    setFiles((was) => [...was, ...documents.filter((one) => !was.some((held) => held.name === one.name))]);
  };
  const picked = (event: ChangeEvent<HTMLInputElement>): void => {
    take(Array.from(event.target.files ?? []));
    event.target.value = "";
  };
  const dropped = (event: DragEvent): void => {
    event.preventDefault();
    setOver(false);
    take(Array.from(event.dataTransfer.files));
  };

  const create = async (): Promise<void> => {
    setRefused(null);
    let landed = 0;
    setSent(0);
    try {
      for (const file of files) {
        await putFile(credentials, name, file.name, await file.text());
        landed += 1;
        setSent(landed);
      }
      onMade(name);
    } catch (failed) {
      // The first file makes the base, so a failure part of the way leaves one: it has to be said.
      setRefused(landed === 0 ? saidBy(failed) : `${saidBy(failed)} ${landed} of ${files.length} landed, so ${name} exists with them. Create it again to send the rest: a file already in is written over.`);
      setSent(null);
    }
  };

  return (
    <div className="kn-new">
      <label className="kn-field">
        Name
        <input className="cfg-input" autoFocus spellCheck={false} placeholder="cleaning-services" value={name} disabled={busy} onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s+/g, "-"))} />
        {nameBad && <span className="cfg-refused">Only a to z, 0 to 9, and single hyphens between words.</span>}
        {clash && <span className="cfg-refused">There is a base called {name} already.</span>}
      </label>

      <label
        className={over ? "kn-dropzone kn-dropzone-over" : "kn-dropzone"}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={dropped}
      >
        <input className="kn-file" type="file" multiple accept=".md,.markdown,.txt,text/markdown,text/plain" aria-label="Documents" disabled={busy} onChange={picked} />
        <span className="kn-dropzone-words">Drop documents here, or click to choose</span>
        <span className="dash-quiet">Markdown or text. Markdown works best: a search finds a passage by its headings.</span>
      </label>
      {skipped > 0 && <p className="cfg-refused">{skipped === 1 ? "One file was left out: only" : `${skipped} files were left out: only`} .md and .txt can be read.</p>}

      {files.length > 0 && (
        <div className="kn-files">
          {files.map((file) => (
            <div key={file.name} className="kn-rule">
              <span className="dash-clip">{file.name}</span>
              <button type="button" className="kn-drop" aria-label={`Leave out ${file.name}`} disabled={busy} onClick={() => setFiles((was) => was.filter((one) => one !== file))}>
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      <div className="kn-new-foot">
        <button type="button" className="app-button" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="cfg-save" disabled={!ready} onClick={() => void create()}>
          {busy ? `Sending ${sent} of ${files.length}…` : using ? "Create and use" : "Create base"}
        </button>
      </div>
    </div>
  );
}
