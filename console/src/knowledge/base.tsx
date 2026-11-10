/** One knowledge base open: a card that says what it is and who searches it, its files as a list, and the file open in the side panel beside them. */

import { useCallback, useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { KnowledgeFiles } from "@pinecall/core/wire/rest-retrieval";
import { ConfirmButton } from "../apps/confirm";
import { ago, count } from "../lib/format";
import { Icon } from "../shell/icons";
import { AgentLink } from "./agent-link";
import { A_DOCUMENT, chunksIn, dropFile, putFile, readFiles, type BaseRead } from "./door";
import { FilePanel } from "./file-panel";

// A short list reads at a glance; a long one gets a search.
const SEARCH_FROM = 9;
const WRITE = "write";

function Fact({ name, title, children }: { name: string; title?: string; children: ReactNode }): ReactNode {
  return (
    <div>
      <dt>{name}</dt>
      <dd className="dash-clip" title={title}>
        {children}
      </dd>
    </div>
  );
}

function Hero({ base, files }: { base: BaseRead; files: KnowledgeFiles | null }): ReactNode {
  return (
    <section className="kb-hero" aria-label={`About ${base.base}`}>
      <div className="kb-hero-top">
        <span className="kb-hero-mark">
          <Icon name="knowledge" size={17} />
        </span>
        <div className="kb-hero-words">
          <h2 className="kb-hero-title dash-clip">{base.base}</h2>
          <p className="kb-hero-by">
            {base.agents.length === 0 ? (
              <span className="dash-quiet">No agent searches it yet. Turn it on in an agent's Knowledge tab.</span>
            ) : (
              <>
                <span className="dash-quiet">Searched by</span>
                {base.agents.map((agent) => (
                  <AgentLink key={agent} name={agent} className="dash-tag" />
                ))}
              </>
            )}
          </p>
        </div>
      </div>
      <dl className="kb-hero-facts">
        <Fact name="Files">{files === null || !files.kept ? "—" : count(files.files.length)}</Fact>
        <Fact name="Chunks">{count(base.chunks)}</Fact>
        <Fact name="Language">
          <span className="dash-first">{base.language === "simple" ? "Not detected" : base.language}</span>
        </Fact>
        <Fact name="Embedder" title={base.model}>
          <span className="kb-mono">{base.model}</span>
        </Fact>
        <Fact name="Updated">{ago(base.pushed_at)}</Fact>
      </dl>
    </section>
  );
}

/** `faq/hours.md` with its folder quiet, so the name is what the eye lands on. */
function PathName({ path }: { path: string }): ReactNode {
  const cut = path.lastIndexOf("/") + 1;
  return (
    <>
      {cut > 0 && <span className="kb-folder">{path.slice(0, cut)}</span>}
      {path.slice(cut)}
    </>
  );
}

export function BaseView({ base, onChanged, onEmptied }: { base: BaseRead; onChanged: () => Promise<void>; onEmptied: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const name = base.base;
  // The address says which panel is open, so there is one at a time.
  const [params, setParams] = useSearchParams();
  const opened = params.get("file");
  const writing = params.get("panel") === WRITE;
  const [files, setFiles] = useState<KnowledgeFiles | null>(null);
  const [filter, setFilter] = useState("");
  const [sent, setSent] = useState<{ landed: number; of: number } | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    try {
      setFiles(await readFiles(credentials, name));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  }, [credentials, name]);

  useEffect(() => {
    void reread();
  }, [reread]);

  const open = (file: string): void => setParams({ file });
  const close = (): void => setParams({});
  const changed = (): Promise<unknown> => Promise.all([reread(), onChanged()]);

  // One at a time: a batch failing part of the way says how far it got.
  const upload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length === 0) return;
    const documents = picked.filter((one) => A_DOCUMENT.test(one.name));
    const left = picked.length - documents.length;
    setSaid(null);
    setRefused(left === 0 ? null : `${left === 1 ? "One file was" : `${left} files were`} left out: only .md and .txt can be read.`);
    if (documents.length === 0) return;
    let landed = 0;
    setSent({ landed, of: documents.length });
    try {
      for (const file of documents) {
        await putFile(credentials, name, file.name, await file.text());
        landed += 1;
        setSent({ landed, of: documents.length });
      }
      setSaid(`${documents.length === 1 ? "One file" : `${documents.length} files`} added`);
    } catch (failed) {
      setRefused(`${saidBy(failed)} ${landed} of ${documents.length} landed.`);
    } finally {
      setSent(null);
      await changed();
    }
  };

  const every = files?.files ?? [];
  const last = every.length === 1;
  const most = Math.max(1, ...every.map((one) => one.chunks));

  const remove = async (path: string): Promise<void> => {
    setSaid(null);
    setRefused(null);
    try {
      await dropFile(credentials, name, path);
      if (opened === path) close();
      await (last ? onEmptied() : changed());
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const typed = filter.trim().toLowerCase();
  const shown = every.filter((one) => one.path.toLowerCase().includes(typed));
  const busy = sent !== null;

  return (
    <div className="kb-page">
      <Hero base={base} files={files} />
      <section className="dash-card" aria-label="Files">
        <div className="kb-bar">
          <span className="dash-eyebrow">Files</span>
          <span className="dash-quiet kb-said" role="status">
            {sent !== null ? `Adding ${sent.landed} of ${sent.of}…` : said}
          </span>
          {every.length >= SEARCH_FROM && <input className="app-input kb-look" aria-label="Search files" placeholder="Search files" value={filter} onChange={(event) => setFilter(event.target.value)} />}
          <label className={busy ? "app-button kb-upload kb-upload-busy" : "app-button kb-upload"}>
            Add files
            <input type="file" multiple accept=".md,.markdown,.txt,text/markdown,text/plain" aria-label="Add files to this base" disabled={busy} onChange={(event) => void upload(event)} />
          </label>
          <button type="button" className="cfg-save" disabled={busy} onClick={() => setParams({ panel: WRITE })}>
            Write a file
          </button>
        </div>
        {refused !== null && (
          <p className="cfg-refused kb-refused" role="alert">
            {refused}
          </p>
        )}
        {files === null ? (
          refused === null && <p className="dash-quiet">Reading the files…</p>
        ) : !files.kept ? (
          <p className="dash-quiet">This base was pushed before its files were kept, so there is nothing to open yet. Push it again from its project, or add a file: from then on they are kept.</p>
        ) : every.length === 0 ? (
          <p className="dash-quiet">No file in this base yet.</p>
        ) : shown.length === 0 ? (
          <p className="dash-quiet">Nothing by that name.</p>
        ) : (
          <div className="kb-rows">
            {shown.map((one) => (
              <div key={one.path} className={opened === one.path ? "kb-row dash-row kb-row-on" : "kb-row dash-row"} onClick={() => open(one.path)}>
                <span className="kb-row-tile">
                  <Icon name="file" size={15} />
                </span>
                <div className="kb-row-main">
                  <button
                    type="button"
                    className="kb-row-title dash-clip"
                    title={one.path}
                    aria-current={opened === one.path ? "true" : undefined}
                    onClick={(event) => {
                      event.stopPropagation();
                      open(one.path);
                    }}
                  >
                    <PathName path={one.path} />
                  </button>
                  <span className="kb-row-under dash-clip">{count(one.chars)} characters</span>
                </div>
                <span className="kb-share" title={`${Math.round((one.chunks / Math.max(1, base.chunks)) * 100)}% of this base`}>
                  <span className="kb-share-track">
                    <span style={{ width: `${Math.max(4, (one.chunks / most) * 100)}%` }} />
                  </span>
                </span>
                <span className="kb-row-count">{chunksIn(one.chunks)}</span>
                <span className="kb-row-date">{ago(one.pushed_at)}</span>
                <span className="kb-row-end" onClick={(event) => event.stopPropagation()}>
                  <ConfirmButton label="Remove" asks={last ? "Removes the base" : "Remove it?"} danger onConfirm={() => void remove(one.path)} />
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
      {opened !== null && <FilePanel key={opened} base={name} path={opened} taken={[]} onClose={close} onKept={() => void changed()} />}
      {writing && (
        <FilePanel
          key="new"
          base={name}
          path={null}
          taken={every.map((one) => one.path)}
          onClose={close}
          onKept={(line) => {
            close();
            setRefused(null);
            setSaid(line);
            void changed();
          }}
        />
      )}
    </div>
  );
}
