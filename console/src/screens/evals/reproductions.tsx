/** Reproduction files a failed run wrote, one per broken golden. */

import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Pill, Refused, SectionLabel } from "../../ui";
import { readReproduction, readWritten, type Reproduction } from "./door";

/**
 * Files from `.pinecall/evals/<run>/`: they hold the verbatim model requests the log does not keep.
 * A green run writes none.
 */
export function Reproductions({ run }: { run: string }): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const [goldens, setGoldens] = useState<string[] | null>(null);
  const [folder, setFolder] = useState("");
  const [open, setOpen] = useState<Reproduction | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    setOpen(null);
    setRefused(null);
    readWritten(credentials, agent, run).then(
      (written) => {
        if (gone) return;
        setGoldens(written.goldens);
        setFolder(written.folder);
      },
      () => {
        // No folder is normal for a green run.
        if (!gone) setGoldens([]);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, run]);

  if (goldens === null || goldens.length === 0) return null;

  const read = async (golden: string): Promise<void> => {
    setRefused(null);
    try {
      setOpen(await readReproduction(credentials, agent, run, golden));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  return (
    <div className="ev-repro">
      <SectionLabel ruled>Reproductions</SectionLabel>
      <div className="ev-repro-body">
        <div className="ui-note">
          {goldens.length} in <span className="ui-fixed">{folder}/</span> — the golden as written, every verdict on it, and the requests the model answered.
        </div>
        <div className="ui-chips">
          {goldens.map((golden) => (
            <button key={golden} type="button" className={open?.golden === golden ? "ui-chip ui-chip-on" : "ui-chip"} onClick={() => void read(golden)}>
              {golden}
            </button>
          ))}
        </div>
        <Refused>{refused}</Refused>
        {open !== null && (
          <div className="ev-repro-open">
            <div className="ev-repro-title">
              {open.golden} · {open.model} <span className="ui-cell-faint">{open.call}</span>
            </div>
            {open.verdicts
              .filter((verdict) => !verdict.passed)
              .map((verdict) => (
                <div key={verdict.metric} className="ev-repro-verdict">
                  <Pill tone="red" small>
                    {verdict.metric}
                  </Pill>
                  <span className="ev-reason">{verdict.reason}</span>
                </div>
              ))}
            <pre className="ui-code ev-asked">{JSON.stringify(open.asked, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
