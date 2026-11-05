/** Phone testing: say which mobile is yours, and call your sandbox agent from it — at the box's test number, or at the org's production numbers. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { meIn } from "../../lib/corners";
import { forgetPhone, readLine, sayPhone, whatAPhoneReaches, type Line } from "../../lib/line";
import { useOrg } from "../../lib/org";
import { useWhoami } from "../../lib/whoami";
import { Button, Card, CardHead, Empty, Input, Page, PageHead, Pill, Refused, SectionLabel, Select, SelectItem, TextAction } from "../../ui";
import "./numbers.css";

/**
 * A call from the person's own phone reaches their sandbox agent: their own copy when `pinecall
 * start` holds one, else the org's own — an app the box hosts, a Studio agent. At the box's test
 * number it is the only thing that answers; at a production number, everybody else still reaches
 * production.
 */
export function PhoneTesting(): ReactNode {
  const credentials = useCredentials();
  const me = meIn(useWhoami());
  const { agents, held } = useOrg();
  const [line, setLine] = useState<Line | null>(null);
  const [number, setNumber] = useState("");
  const [agent, setAgent] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    setLine(await readLine(credentials));
  }, [credentials]);

  useEffect(() => {
    reread().catch((failed: unknown) => setRefused(saidBy(failed)));
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

  const slugs = agents.map((one) => one.slug);
  const mine = held.filter((one) => me !== null && one.holder?.holder === me).map((one) => one.slug);
  const calling = line?.calling ?? [];
  const testLine = line?.test_line ?? null;
  const reaches = line === null ? null : whatAPhoneReaches(line, slugs, mine);

  return (
    <Page width={900}>
      <PageHead
        title="Phone testing"
        ledeWidth={660}
        lede={
          <>
            Say which mobile is yours, once. A call from it reaches <b>your sandbox agent</b>: at Pinecall&apos;s test number, with no number of your own, or at one of your production
            numbers, where everybody else still reaches production.
          </>
        }
      />

      <Card>
        <CardHead title="Your mobile" meta={calling.length === 0 ? "none yet" : calling.map(prettyNumber).join(", ")} />
        <div className="num-body">
          {calling.length > 0 ? (
            <div className="num-dial-row">
              <span>
                {calling.map(prettyNumber).join(", ")} is yours{line?.agent ? `, and reaches ${line.agent}` : ""}.
              </span>
              <TextAction onClick={() => void forget()}>Forget</TextAction>
            </div>
          ) : (
            <form className={slugs.length > 1 ? "num-fields num-fields-3" : "num-fields"} onSubmit={(event) => void say(event)}>
              <Input value={number} placeholder="With the country code: +34600000000" autoComplete="tel" aria-label="Your mobile" onChange={(event) => setNumber(event.target.value)} />
              {slugs.length > 1 && (
                <Select value={agent} onValueChange={setAgent} placeholder="The agent it reaches" aria-label="The agent a call from this phone reaches">
                  {slugs.map((slug) => (
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
          {reaches !== null && (
            <div className="num-dial-row">
              <Pill tone={reaches.tone}>a call from it reaches</Pill>
              <span>{reaches.said}</span>
            </div>
          )}
          <Refused>{refused}</Refused>
        </div>
        <div className="ui-card-foot">
          <SectionLabel>The same, from the terminal</SectionLabel>
          <pre className="ui-code">{"pinecall line from +34600000000       # this mobile is mine; --agent <name> says which agent\npinecall line forget                  # forget it"}</pre>
        </div>
      </Card>

      <Card>
        <CardHead title="Then call" />
        <div className="num-body">
          {testLine !== null ? (
            <>
              <span className="num-dial">{prettyNumber(testLine)}</span>
              <span className="num-note">
                Pinecall&apos;s test number. Only a phone somebody said was theirs reaches an agent here; from any other it says so. The call is yours, in the sandbox, and counts
                against its minutes.
              </span>
            </>
          ) : (
            <Empty>This box has no test number: an operator sets one under Box settings ▸ Routes. Your production numbers below work the same way.</Empty>
          )}
        </div>
      </Card>

      {line !== null && line.numbers.length > 0 && (
        <Card>
          <CardHead title="Or one of your production numbers" meta="your phone reaches the sandbox; everybody else, production" />
          {line.numbers.map((one) => (
            <div key={one.number} className="num-row">
              <span className="num-number">{prettyNumber(one.number)}</span>
              <span className="num-arrow" aria-hidden>
                →
              </span>
              <span className="num-agent">{one.agent}</span>
              <span className="num-end">
                {calling.length === 0 ? (
                  <Pill tone="gray">production answers: say which phone is yours</Pill>
                ) : slugs.includes(one.agent) ? (
                  <Pill tone="green">your phone reaches the sandbox copy</Pill>
                ) : (
                  <Pill tone="amber">production answers: nobody runs {one.agent} in the sandbox</Pill>
                )}
              </span>
            </div>
          ))}
        </Card>
      )}
    </Page>
  );
}
