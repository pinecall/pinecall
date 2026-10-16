/** Notifications screen: which call events notify this person, on this browser and their phones. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { forgetDevice, readNotices, saveNotices, sendTestNotice, type Notices, type NoticesChanged } from "@pinecall/core/notify";
import { WORLD } from "../../lib/mode";
import { theNotifier } from "../../lib/notifier";
import { Button, Card, CardHead, Empty, Item, Page, PageHead, Refused, Switch } from "../../ui";
import { useDoor, useMove } from "../box/use-door";
import { type Standing, useThisBrowser } from "./use-this-browser";
import "./notifications.css";

const SAID: Record<Standing, string> = {
  unknown: "Checking this browser…",
  unsupported: "This browser cannot show notifications from a page.",
  blocked: "Notifications are blocked for this site: allow them in the browser's site settings.",
  off: "Off. Turn it on to be told even with the console closed.",
  on: "On. This browser is told about the calls below.",
};

const PLATFORM: Record<string, string> = { web: "Browser", android: "Android phone", ios: "iPhone" };

export function Notifications(): ReactNode {
  const credentials = useCredentials();
  const notifier = theNotifier(credentials);
  const notices = useDoor(useCallback(() => readNotices(theNotifier(credentials)), [credentials]));
  const browser = useThisBrowser(credentials);
  const acting = useMove();
  const [chosen, setChosen] = useState<Notices | undefined>(undefined);
  const [tested, setTested] = useState<string | null>(null);

  useEffect(() => setChosen(notices.value), [notices.value]);

  // Saves on toggle; the notifier returns the full updated settings.
  const change = (changed: NoticesChanged): void => {
    void acting.move(async () => setChosen(await saveNotices(notifier, changed)));
  };

  // Shows per-device results; if the push service dropped this browser, resubscribe and say so.
  const test = (): void => {
    setTested(null);
    void acting.move(async () => {
      const answer = await sendTestNotice(notifier);
      const mine = answer.failed.find((one) => one.device === browser.deviceId);
      if (mine?.dead) {
        await browser.renew();
        await notices.reread();
        setTested("This browser's subscription had expired; it was renewed. Send the test again.");
        return;
      }
      const took = answer.sent === 0 ? "No device took it" : `Sent to ${answer.sent} device${answer.sent === 1 ? "" : "s"}`;
      const why = answer.failed.map((one) => `${nameOf(one.device)}: ${one.error}`).join("; ");
      setTested(why === "" ? `${took}.` : `${took}. Failed — ${why}.`);
    });
  };

  const nameOf = (device: string): string => {
    const known = chosen?.devices.find((one) => one.id === device);
    return known === undefined ? "a device since forgotten" : (known.label ?? PLATFORM[known.platform] ?? known.platform);
  };

  const move = (what: () => Promise<void>): void => {
    void acting.move(async () => {
      await what();
      await notices.reread();
    });
  };

  const org = chosen?.org_name ?? "this org";
  // Each world's console chooses for its own calls; the sandbox starts silent.
  const calls = WORLD === "sandbox" ? "sandbox calls" : "calls";

  return (
    <Page width={760}>
      <PageHead title="Notifications" lede={`What you are told about ${org}'s ${calls}, on this browser and on your phone, even when nothing of Pinecall is open.`} />
      <Refused>{notices.refused ?? acting.refused}</Refused>

      <Card>
        <CardHead title="This browser" meta={SAID[browser.standing]} />
        <div className="notices-line">
          {browser.standing === "off" && (
            <Button kind="primary" size="md" disabled={acting.busy} onClick={() => move(browser.turnOn)}>
              Turn on
            </Button>
          )}
          {browser.standing === "on" && (
            <Button size="md" disabled={acting.busy} onClick={() => move(browser.turnOff)}>
              Turn off
            </Button>
          )}
          <Button size="md" disabled={acting.busy || (chosen?.devices.length ?? 0) === 0} onClick={test}>
            Send a test
          </Button>
          {tested !== null && <span className="notices-done">{tested}</span>}
        </div>
      </Card>

      {chosen !== undefined && (
        <Card>
          <CardHead title="What to tell you" meta={`of ${org}'s ${calls}, on every device of yours`} />
          <Choice name="A call asks for a person" sub="The agent put the caller on hold and is waiting for somebody to take the line." on={chosen.events.attention} onChange={(on) => change({ events: { attention: on } })} />
          <Choice name="Every incoming call" sub="Each call as it starts ringing, whoever answers it." on={chosen.events.ringing} onChange={(on) => change({ events: { ringing: on } })} />
          <Choice name="A monitor fires" sub="A number the org watches crossed its line over its window: latency, the judges, escalations, tools, spend. Once a day per monitor." on={chosen.events.monitors} onChange={(on) => change({ events: { monitors: on } })} />
        </Card>
      )}

      {chosen !== undefined && (
        <Card>
          <CardHead title="Your devices" meta="yours in every org you belong to; what each org tells them is the choice above" />
          {chosen.devices.length === 0 ? (
            <Empty>No device yet. Turn this browser on, or open Notificaciones in Pinecall on your phone.</Empty>
          ) : (
            chosen.devices.map((device) => {
              // This browser's own row is turned off, so its subscription goes with it.
              const mine = device.id === browser.deviceId;
              const forget = mine ? browser.turnOff : () => forgetDevice(notifier, device.id);
              return (
                <Item
                  key={device.id}
                  name={device.label ?? PLATFORM[device.platform]}
                  sub={mine ? `${PLATFORM[device.platform]} · this one` : PLATFORM[device.platform]}
                  end={
                    <Button size="xs" disabled={acting.busy} onClick={() => move(forget)}>
                      Remove
                    </Button>
                  }
                />
              );
            })
          )}
        </Card>
      )}
    </Page>
  );
}

function Choice({ name, sub, on, onChange }: { name: string; sub: string; on: boolean; onChange: (on: boolean) => void }): ReactNode {
  return <Item name={name} sub={sub} end={<Switch on={on} onChange={onChange} label={name} />} />;
}
