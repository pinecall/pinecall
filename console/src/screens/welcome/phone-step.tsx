/** Step: which mobile is yours, said here, so a call from it reaches the copy running on your computer. */

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { prettyNumber } from "@pinecall/core/calls";
import { drop, put, read, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Input, Refused, TextAction } from "../../ui";
import { Command } from "./command";
import type { Routed } from "./number-step";

export function PhoneStep({ routed, running }: { routed: Routed[] | null; running: boolean }): ReactNode {
  const credentials = useCredentials();
  // A phone is said in the sandbox, whichever console this is: it is the sandbox copy a call reaches.
  const sandbox = useMemo(() => ({ ...credentials, world: "sandbox" as const }), [credentials]);
  const [calling, setCalling] = useState<string[]>([]);
  const [number, setNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    const answer = (await read(sandbox, "/v1/line/numbers")) as { calling?: string[] };
    setCalling(answer.calling ?? []);
  }, [sandbox]);

  useEffect(() => {
    reread().catch(() => undefined);
  }, [reread]);

  const say = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      await put(sandbox, "/v1/line/from", { number: number.trim() });
      setNumber("");
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (): Promise<void> => {
    setRefused(null);
    try {
      await drop(sandbox, "/v1/line/from");
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const [dial] = routed ?? [];
  return (
    <>
      <p className="wel-lead">
        Tell Pinecall which mobile is yours. Then, while <code className="wel-inline">pinecall start</code> runs on your computer, a call from that phone reaches <b>your copy</b>, with the
        conversation in your terminal. Everybody else who calls the number still reaches production.
      </p>
      <div className="wel-block">
        {calling.length > 0 ? (
          <div className="wel-waiting wel-waiting-ok">
            ✓ Calls from {calling.map(prettyNumber).join(", ")} reach your copy{running ? "" : ", once pinecall start is running"}.{" "}
            <TextAction onClick={() => void forget()}>Forget</TextAction>
          </div>
        ) : (
          <form className="wel-form" onSubmit={(event) => void say(event)}>
            <Input value={number} placeholder="Your mobile, with the country code: +34600000000" autoComplete="tel" onChange={(event) => setNumber(event.target.value)} />
            <Button kind="primary" size="form" type="submit" disabled={busy || number.trim() === ""}>
              {busy ? "Saving…" : "This phone is mine"}
            </Button>
          </form>
        )}
        <Refused>{refused}</Refused>
        <span className="wel-hint">The same, from the terminal:</span>
        <Command line="pinecall line from +34600000000" />
      </div>
      <div className="wel-block">
        <strong>Then call</strong>
        {dial === undefined ? (
          <span className="wel-hint">Your org has no number yet: the step before gets one. Once it has, this says which to dial.</span>
        ) : (
          <span className="wel-hint">
            Dial <b className="wel-number-digits">{prettyNumber(dial.number)}</b> from that phone. {dial.agent} answers from your computer, and the call appears in Calls the moment it
            starts, marked as diverted from production.
          </span>
        )}
      </div>
    </>
  );
}
