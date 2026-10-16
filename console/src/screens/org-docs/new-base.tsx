/** New knowledge base form: a name and its first documents. */

import { useState, type ChangeEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Input, Segmented, TextArea } from "../../ui";
import { putFile } from "./door";

// Same rule as `pinecall docs push --base`.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

type First = "upload" | "write";

/** The gateway has no empty bases: the first file creates one, so name and files are asked together. */
export function NewBase({ taken, onCancel }: { taken: readonly string[]; onCancel: () => void }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [first, setFirst] = useState<First>("upload");
  const [picked, setPicked] = useState<File[]>([]);
  const [path, setPath] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // Files already uploaded: a partial failure still leaves a base, so the error must name it.
  const [landed, setLanded] = useState<string[]>([]);

  const nameOk = A_NAME.test(name);
  const clash = taken.includes(name);
  const somethingIn = first === "upload" ? picked.length > 0 : path.trim() !== "" && text.trim() !== "";
  const ready = nameOk && !clash && somethingIn && !busy;
  const asked = first === "upload" ? picked.length : 1;

  const pick = (event: ChangeEvent<HTMLInputElement>): void => setPicked(Array.from(event.target.files ?? []));

  const create = async (): Promise<void> => {
    setBusy(true);
    setRefused(null);
    setLanded([]);
    const inside: string[] = [];
    try {
      if (first === "upload") {
        for (const file of picked) {
          await putFile(credentials, name, file.name, await file.text());
          inside.push(file.name);
        }
      } else {
        await putFile(credentials, name, path.trim(), text);
        inside.push(path.trim());
      }
      void navigate(`/docs/${encodeURIComponent(name)}`);
    } catch (failed) {
      setRefused(failed instanceof Error ? failed.message : String(failed));
      setLanded(inside);
      setBusy(false);
    }
  };

  return (
    <div className="ui-card nb">
      <div className="ui-card-head">
        <span className="ui-card-title">New base</span>
        <span className="ui-card-meta">a set of documents an agent searches</span>
      </div>
      <div className="nb-body">
        <label className="nb-field">
          <span className="nb-label">Name</span>
          <span className="nb-hint">How agents attach it, in their Settings ▸ Bases. Lower-case words joined by hyphens.</span>
          <Input value={name} spellCheck={false} placeholder="cleaning-services" onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s+/g, "-"))} />
          {name !== "" && !nameOk && <span className="nb-bad">Only a–z, 0–9 and single hyphens between words.</span>}
          {clash && <span className="nb-bad">There is a base called {name} already: open it to add files.</span>}
        </label>

        <div className="nb-field">
          <span className="nb-label">First documents</span>
          <span className="nb-hint">A base starts with at least one. Markdown works best: its headings are what a search finds a passage by.</span>
          <Segmented
            options={[
              { value: "upload", label: "Upload files" },
              { value: "write", label: "Write one" },
            ]}
            value={first}
            onChange={setFirst}
          />
          {first === "upload" ? (
            <label className="nb-drop">
              <input type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" multiple aria-label="The base’s first files" onChange={pick} />
              {picked.length === 0 ? (
                <span>Choose .md or .txt files — several at once</span>
              ) : (
                <span>
                  {picked.length} file{picked.length === 1 ? "" : "s"}: {picked.map((one) => one.name).join(", ")}
                </span>
              )}
            </label>
          ) : (
            <>
              <Input value={path} spellCheck={false} placeholder="its path in the base: services/move-out.md" aria-label="Its path in the base" onChange={(event) => setPath(event.target.value)} />
              <TextArea rows={8} value={text} spellCheck={false} aria-label="The document" placeholder={"# Move-out cleaning\n\nWhat is included, how long it takes, how to prepare."} onChange={(event) => setText(event.target.value)} />
            </>
          )}
        </div>
      </div>
      <div className="nb-foot">
        <Button kind="primary" size="form" disabled={!ready} onClick={() => void create()}>
          {busy ? "Creating…" : "Create base"}
        </Button>
        <Button size="form" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {refused !== null && (
        <p className="nb-landed">
          <span className="nb-bad">{refused}</span>
          {landed.length === 0 ? (
            <span>Nothing landed: there is no base called {name}. Nothing was made under that name, so create it again once the refusal above is answered.</span>
          ) : (
            <span>
              {landed.length} of {asked} landed, so the base <b>{name}</b> exists already with {landed.join(", ")}. Create again to send the rest — a file that is in is
              written over, not doubled — or <Link to={`/docs/${encodeURIComponent(name)}`}>open {name}</Link> and add them there.
            </span>
          )}
        </p>
      )}
    </div>
  );
}
