/** Knowledge base screen: list, edit, upload and delete its files. */

import { useCallback, useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { type KnowledgeFiles } from "@pinecall/core/wire/rest-retrieval";

import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { useWayBack } from "../../lib/whence";
import { Button, Card, CardHead, Empty, Page, PageHead, Refused, TableHead, TableRow, TextAction } from "../../ui";
import { dropFile, putFile, readFile, readFiles } from "./door";
import { MarkdownPreview } from "./preview";
import "./org-docs.css";

const COLUMNS = "minmax(0,1fr) 110px 90px 150px 70px";
const NEW = "new";

function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

// The open file is `?file=`; `?file=new` is an unsaved file with no path yet.
export function OrgBase(): ReactNode {
  const credentials = useCredentials();
  const base = useParams()["base"] ?? "";
  const [params, setParams] = useSearchParams();
  const opened = params.get("file");
  const [files, setFiles] = useState<KnowledgeFiles | null>(null);
  const [path, setPath] = useState("");
  const [text, setText] = useState("");
  const [was, setWas] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  // A file opens to be read, drawn as the page it is; editing is one click away, and a new file starts there.
  const [editing, setEditing] = useState(false);

  const reread = useCallback(async (): Promise<void> => {
    setFiles(await readFiles(credentials, base));
  }, [credentials, base]);

  useEffect(() => {
    let gone = false;
    reread().catch((failed: unknown) => {
      if (!gone) setRefused(saidBy(failed));
    });
    return () => {
      gone = true;
    };
  }, [reread]);

  useEffect(() => {
    let gone = false;
    setSaid(null);
    setEditing(opened === NEW);
    if (opened === null) return;
    if (opened === NEW) {
      setPath("");
      setText("");
      setWas("");
      return;
    }
    readFile(credentials, base, opened).then(
      (read) => {
        if (gone) return;
        setPath(read.path);
        setText(read.text);
        setWas(read.text);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, base, opened]);

  const open = (file: string | null): void => setParams(file === null ? {} : { file });

  const save = async (): Promise<void> => {
    const named = path.trim();
    if (named === "") {
      setRefused("name the file first: a path like faq/horarios.md");
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      const pushed = await putFile(credentials, base, named, text);
      setWas(text);
      setSaid(`${pushed.path} kept · ${pushed.chunks} chunk${pushed.chunks === 1 ? "" : "s"} · ${Math.round(pushed.took_ms)} ms`);
      await reread();
      if (opened !== named) open(named);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (named: string): Promise<void> => {
    if (!window.confirm(`Take ${named} out of ${base}? The agent stops searching it on the next call.`)) return;
    setRefused(null);
    try {
      await dropFile(credentials, base, named);
      if (opened === named) open(null);
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  // Upload sequentially and open the last file.
  const upload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length === 0) return;
    setBusy(true);
    setRefused(null);
    try {
      for (const file of picked) await putFile(credentials, base, file.name, await file.text());
      await reread();
      open(picked[picked.length - 1]!.name);
      setSaid(`${picked.length} file${picked.length === 1 ? "" : "s"} added`);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const changed = text !== was || (opened === NEW && path.trim() !== "");
  // Reachable from org Docs and from an agent, so back returns to the origin.
  const back = useWayBack("/docs");

  return (
    <Page width={1060}>
      <PageHead
        title={base}
        back={<Link to={back.to}>← {back.name}</Link>}
        ledeWidth={640}
        lede="The documents the agent searches, one file each. Open one to read or change it, add one from your disk or write it here, take one out. Every change is searchable on the next call."
        actions={
          <div className="od-actions">
            <label className={busy ? "ui-button ui-button-form od-upload od-busy" : "ui-button ui-button-form od-upload"}>
              Add files…
              <input type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" multiple disabled={busy} aria-label="Add files to this base" onChange={(event) => void upload(event)} />
            </label>
            <Button kind="primary" size="form" disabled={busy} onClick={() => open(NEW)}>
              Write one
            </Button>
          </div>
        }
      />

      <Refused>{refused}</Refused>

      <Card>
        <CardHead title="Files" meta={files === null ? undefined : `${files.files.length} file${files.files.length === 1 ? "" : "s"}`} />
        {files === null ? (
          <Empty>{refused === null ? "Asking the gateway…" : "The files could not be read."}</Empty>
        ) : !files.kept ? (
          <Empty>
            This base was pushed before its files were kept, so there is nothing to open here yet. Push it again from its project (`pinecall docs push`), or add a file: from then on the files are kept.
          </Empty>
        ) : files.files.length === 0 ? (
          <Empty>No file in this base. Add one above.</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["File", "Characters", "Chunks", "Arrived", ""]} />
            {files.files.map((one) => (
              <TableRow key={one.path} columns={COLUMNS} onClick={() => open(one.path)}>
                <span className={opened === one.path ? "ui-cell-strong ui-clip od-open" : "ui-cell-strong ui-clip"}>{one.path}</span>
                <span className="ui-cell">{one.chars.toLocaleString("en-US")}</span>
                <span className="ui-cell">{one.chunks}</span>
                <span className="ui-cell">{dayAndTime(one.pushed_at)}</span>
                <span className="ui-cell od-row-end">
                  <TextAction danger onClick={() => void remove(one.path)}>
                    Take out
                  </TextAction>
                </span>
              </TableRow>
            ))}
          </>
        )}
      </Card>

      {opened !== null && (
        <Card>
          <CardHead title={opened === NEW ? "A new file" : opened} meta={opened === NEW ? undefined : `${text.length.toLocaleString("en-US")} characters`}>
            {opened !== NEW && (
              <span className="od-mode" role="group" aria-label="how the file is shown">
                <button type="button" className={editing ? "od-mode-one" : "od-mode-one od-mode-on"} onClick={() => setEditing(false)}>
                  Read
                </button>
                <button type="button" className={editing ? "od-mode-one od-mode-on" : "od-mode-one"} onClick={() => setEditing(true)}>
                  Edit
                </button>
              </span>
            )}
            <TextAction onClick={() => open(null)}>Close</TextAction>
          </CardHead>
          {!editing && (
            <div className="od-read">
              <MarkdownPreview markdown={text} />
            </div>
          )}
          <div className="od-editor" hidden={!editing}>
            {opened === NEW && (
              <input className="ui-input od-path" value={path} placeholder="its path in the base: faq/horarios.md" spellCheck={false} aria-label="Its path in the base" onChange={(event) => setPath(event.target.value)} />
            )}
            <textarea
              className="ui-textarea od-text"
              value={text}
              spellCheck={false}
              aria-label={opened === NEW ? "The new file" : opened}
              placeholder={"# Horarios\n\nDe lunes a viernes, de 9:00 a 20:00."}
              onChange={(event) => setText(event.target.value)}
            />
            <div className="od-editor-foot">
              <Button kind="primary" size="form" disabled={busy || !changed} onClick={() => void save()}>
                {busy ? "Keeping…" : opened === NEW ? "Add to the base" : "Save"}
              </Button>
              <span className="od-said">{said ?? (changed ? "Not kept yet." : "Markdown. Headings are what a search finds a passage by.")}</span>
            </div>
          </div>
        </Card>
      )}
    </Page>
  );
}
