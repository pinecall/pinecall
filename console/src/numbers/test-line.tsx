/** The phone a person tests from: which mobile is theirs, said once, and the test number that reaches their agent in the sandbox from it. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Select } from "../ui/select";
import { forgetPhone, readLine, sayPhone, type Line } from "./door";
import { Copy } from "./parts";
import { e164, shown } from "./words";

/** `agent` is the one the card was drawn for: it is who the mobile reaches, with no choice shown. Draws nothing where there is no test line to call. */
export function TestLine({ agents, agent: fixed }: { agents: readonly string[]; agent?: string | undefined }): ReactNode {
  const credentials = useCredentials();
  const [line, setLine] = useState<Line | null>(null);
  const [mobile, setMobile] = useState("");
  const [picked, setPicked] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readLine(credentials).then((read) => !gone && setLine(read), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials]);

  const act = useCallback(async (doing: () => Promise<Line | null>): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      setLine(await doing());
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  }, []);

  if (line === null || line.test_line == null) return null;
  const agent = fixed ?? (agents.includes(picked) ? picked : (line.agent ?? agents[0] ?? ""));
  const mine = line.calling[0];
  const say = (event: FormEvent): void => {
    event.preventDefault();
    void act(() => sayPhone(credentials, e164(mobile), agent)).then(() => setMobile(""));
  };
  const reaches = line.agent ?? null;

  return (
    <section className="num-test" aria-label="Call from your mobile" title="Only calls from your own mobile reach your agent at this number.">
      <span className="num-test-title">Call from your mobile</span>
      {mine === undefined ? (
        <form className="num-test-form" onSubmit={say}>
          <input className="cfg-input" aria-label="Your mobile" placeholder="Your mobile: +34 600 000 000" required autoComplete="tel" value={mobile} onChange={(event) => setMobile(event.target.value)} />
          {fixed === undefined && agents.length > 1 && <Select label="Agent it reaches" searchable={false} items={agents.map((one) => ({ value: one, label: one }))} value={agent} onChange={setPicked} />}
          <button type="submit" className="app-button" disabled={busy || agent === ""}>
            {busy ? "Saving…" : "Save"}
          </button>
        </form>
      ) : (
        <>
          <Copy text={shown(line.test_line)} bare />
          <span className="num-test-from dash-clip">from {shown(mine)}</span>
          {fixed !== undefined && reaches !== fixed && (
            <button type="button" className="app-button" disabled={busy} onClick={() => void act(() => sayPhone(credentials, mine, fixed))}>
              Reach {fixed} instead
            </button>
          )}
          {fixed === undefined && agents.length > 1 && <Select label="Agent it reaches" searchable={false} items={agents.map((one) => ({ value: one, label: `Reaches ${one}` }))} value={reaches ?? ""} placeholder="Pick the agent" onChange={(next) => void act(() => sayPhone(credentials, mine, next))} />}
          <button type="button" className="num-link" disabled={busy} onClick={() => void act(async () => (await forgetPhone(credentials), readLine(credentials)))}>
            Forget
          </button>
        </>
      )}
      {refused !== null && <p className="cfg-refused num-test-refused">{refused}</p>}
    </section>
  );
}
