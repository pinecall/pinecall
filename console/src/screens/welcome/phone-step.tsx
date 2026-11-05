/** Step: which mobile is yours, said here, and the number to call it from so your agent answers in the sandbox. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { prettyNumber } from "@pinecall/core/calls";
import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import { forgetPhone, readLine, sayPhone, whatAPhoneReaches, type Line } from "../../lib/line";
import { Button, Input, Refused, Select, SelectItem, TextAction } from "../../ui";
import { Command } from "./command";
import type { Routed } from "./number-step";

export function PhoneStep({ agents, routed }: { agents: HeldAgent[]; routed: Routed[] | null }): ReactNode {
  const credentials = useCredentials();
  const [line, setLine] = useState<Line | null>(null);
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const held = agents.map((one) => one.slug);

  const reread = useCallback(async (): Promise<void> => {
    setLine(await readLine(credentials));
  }, [credentials]);

  useEffect(() => {
    reread().catch(() => undefined);
  }, [reread]);

  const say = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      setLine(await sayPhone(credentials, number.trim(), agent === "" ? null : agent));
      setNumber("");
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (): Promise<void> => {
    setRefused(null);
    try {
      await forgetPhone(credentials);
      await reread();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const calling = line?.calling ?? [];
  const testLine = line?.test_line ?? null;
  const [dial] = routed ?? [];
  const reaches = line === null ? null : whatAPhoneReaches(line, held, []);
  return (
    <>
      <p className="wel-lead">
        Tell Pinecall which mobile is yours, once. Then call Pinecall&apos;s test number from it and <b>your agent answers</b>, here in the sandbox: nothing to buy, no card. The
        call shows up in Calls as it happens.
      </p>
      <div className="wel-block">
        {calling.length > 0 ? (
          <div className="wel-waiting wel-waiting-ok">
            ✓ {calling.map(prettyNumber).join(", ")} is yours{line?.agent ? `, and reaches ${line.agent}` : ""}. <TextAction onClick={() => void forget()}>Forget</TextAction>
          </div>
        ) : (
          <form className="wel-form" onSubmit={(event) => void say(event)}>
            <Input value={number} placeholder="Your mobile, with the country code: +34600000000" autoComplete="tel" onChange={(event) => setNumber(event.target.value)} />
            {held.length > 1 && (
              <Select value={agent} onValueChange={setAgent} placeholder="The agent it reaches" aria-label="The agent a call from this phone reaches">
                {held.map((slug) => (
                  <SelectItem key={slug} value={slug}>
                    {slug}
                  </SelectItem>
                ))}
              </Select>
            )}
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
        {testLine !== null ? (
          <>
            <span className="wel-dial">{prettyNumber(testLine)}</span>
            <span className="wel-hint">
              {reaches === null ? "" : `From that phone. It reaches: ${reaches.said}`}
            </span>
          </>
        ) : dial !== undefined ? (
          <span className="wel-hint">
            Dial <b className="wel-number-digits">{prettyNumber(dial.number)}</b> from that phone: {dial.agent} answers from the sandbox, and the call appears in Calls marked as
            diverted from production.
          </span>
        ) : (
          <span className="wel-hint">This box has no test number yet, and your org no number of its own: the next step gets one.</span>
        )}
      </div>
    </>
  );
}
