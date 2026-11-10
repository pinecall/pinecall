/** Notifications: what this person is told about the org's calls, on this browser and on their phones, and the devices that are told. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { forgetDevice, readNotices, saveNotices, sendTestNotice, type Notices, type NoticesChanged } from "@pinecall/core/notify";
import { ConfirmButton } from "../apps/confirm";
import { theNotifier } from "../lib/notifier";
import { WORLD } from "../lib/world";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { Toggle } from "../ui/setting";
import { useThisBrowser, type Standing } from "./use-this-browser";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../test/test.css";
import "./notifications.css";

const STANDING: Record<Standing, { mood: "held" | "none" | "broke" | "waiting"; word: string; says: string }> = {
  unknown: { mood: "none", word: "Checking", says: "Looking at this browser…" },
  unsupported: { mood: "none", word: "Not possible here", says: "This browser cannot show notifications from a page. Your phone can: install Pinecall on it." },
  blocked: { mood: "broke", word: "Blocked", says: "Notifications are blocked for this site. Allow them in the browser's site settings, then come back." },
  off: { mood: "waiting", word: "Off", says: "Turn it on to be told even with the console closed." },
  on: { mood: "held", word: "On", says: "This browser is told about the calls below, even with the console closed." },
};

const PLATFORMS: Record<string, { name: string; icon: IconName }> = { web: { name: "Browser", icon: "panel" }, android: { name: "Android phone", icon: "numbers" }, ios: { name: "iPhone", icon: "numbers" } };

function Head({ icon, title, about, children }: { icon: IconName; title: string; about: string; children?: ReactNode }): ReactNode {
  return (
    <header className="tst-head">
      <span className="tst-head-mark" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <span className="tst-head-words">
        <span className="tst-head-title">{title}</span>
        <span className="tst-head-about">{about}</span>
      </span>
      {children}
    </header>
  );
}

function Choice({ name, about, on, disabled, onChange }: { name: string; about: string; on: boolean; disabled: boolean; onChange: (on: boolean) => void }): ReactNode {
  return (
    <div className="tst-row ntf-row">
      <span className="tst-row-words">
        <span className="tst-row-name">{name}</span>
        <span className="tst-row-under">{about}</span>
      </span>
      <Toggle on={on} label={name} disabled={disabled} onChange={onChange} />
    </div>
  );
}

export function NotificationsPage(): ReactNode {
  const credentials = useCredentials();
  const browser = useThisBrowser(credentials);
  const [notices, setNotices] = useState<Notices | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => setNotices(await readNotices(theNotifier(credentials))), [credentials]);
  useEffect(() => {
    reread().catch((failed: unknown) => setRefused(saidBy(failed)));
  }, [reread]);

  /** One move at a time: its refusal is said, and the list is read again after. */
  const move = (doing: () => Promise<void>, again = true): void => {
    setBusy(true);
    setRefused(null);
    doing()
      .then(() => (again ? reread() : undefined))
      .catch((failed: unknown) => setRefused(saidBy(failed)))
      .finally(() => setBusy(false));
  };
  const change = (changed: NoticesChanged): void => move(async () => setNotices(await saveNotices(theNotifier(credentials), changed)), false);

  const nameOf = (device: string): string => {
    const known = notices?.devices.find((one) => one.id === device);
    return known === undefined ? "a device since forgotten" : (known.label ?? PLATFORMS[known.platform]?.name ?? known.platform);
  };

  // A test says how it went on each device; a browser the push service dropped is subscribed again, and said so.
  const test = (): void => {
    setTested(null);
    move(async () => {
      const answer = await sendTestNotice(theNotifier(credentials));
      if (answer.failed.find((one) => one.device === browser.deviceId)?.dead === true) {
        await browser.renew();
        return setTested("This browser's subscription had expired and was renewed. Send the test again.");
      }
      const took = answer.sent === 0 ? "No device took it" : `Sent to ${answer.sent} device${answer.sent === 1 ? "" : "s"}`;
      const why = answer.failed.map((one) => `${nameOf(one.device)}: ${one.error}`).join("; ");
      setTested(why === "" ? `${took}.` : `${took}. Failed: ${why}.`);
    });
  };

  const standing = STANDING[browser.standing];
  const devices = notices?.devices ?? [];
  const org = notices?.org_name ?? "this organization";
  const calls = WORLD === "sandbox" ? "sandbox calls" : "calls";

  return (
    <>
      <PageHead />
      <div className="tst ntf">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}

        <section className="tst-list" aria-label="This browser">
          <Head icon="panel" title="This browser" about={standing.says}>
            <span className={`tst-status ntf-status tst-status-${standing.mood}`}>{standing.word}</span>
            {browser.standing === "off" && (
              <button type="button" className="cfg-save" disabled={busy} onClick={() => move(browser.turnOn)}>
                Turn on
              </button>
            )}
            {browser.standing === "on" && (
              <button type="button" className="app-button" disabled={busy} onClick={() => move(browser.turnOff)}>
                Turn off
              </button>
            )}
          </Head>
        </section>

        <section className="tst-list" aria-label="What to tell you">
          <Head icon="bell" title="What to tell you" about={`Of ${org}'s ${calls}, on every device of yours.`} />
          {notices === null ? (
            <p className="dash-quiet tst-none">{refused === null ? "Reading…" : "The notifier did not answer."}</p>
          ) : (
            <>
              <Choice name="A call asks for a person" about="The agent put the caller on hold and waits for somebody to take the line." on={notices.events.attention} disabled={busy} onChange={(on) => change({ events: { attention: on } })} />
              <Choice name="Every incoming call" about="Each call as it starts ringing, whoever answers it." on={notices.events.ringing} disabled={busy} onChange={(on) => change({ events: { ringing: on } })} />
              <Choice name="A monitor fires" about="A number the org watches crossed its line. Once a day per monitor." on={notices.events.monitors} disabled={busy} onChange={(on) => change({ events: { monitors: on } })} />
            </>
          )}
          <Link to="/monitors" className="tst-link ntf-more">
            Monitors and every alert kept
          </Link>
        </section>

        <section className="tst-list" aria-label="Your devices">
          <Head icon="numbers" title="Your devices" about="Where you are told. They are yours in every organization you belong to.">
            <button type="button" className="app-button" disabled={busy || devices.length === 0} onClick={test}>
              Send a test
            </button>
          </Head>
          {tested !== null && <p className="ntf-tested">{tested}</p>}
          {devices.map((device) => {
            // This browser's own row is turned off, so its subscription goes with it.
            const mine = device.id === browser.deviceId;
            const platform = PLATFORMS[device.platform] ?? { name: device.platform, icon: "panel" as const };
            return (
              <div key={device.id} className="tst-row ntf-row">
                <span className="tst-mark" aria-hidden="true">
                  <Icon name={platform.icon} size={14} />
                </span>
                <span className="tst-row-words">
                  <span className="tst-row-name">
                    <span className="dash-clip">{device.label ?? platform.name}</span>
                    {mine && <span className="tst-tag">this one</span>}
                  </span>
                  <span className="tst-row-under">{platform.name}</span>
                </span>
                <ConfirmButton label="Remove" asks="Stop telling it?" danger onConfirm={() => move(mine ? browser.turnOff : () => forgetDevice(theNotifier(credentials), device.id))} />
              </div>
            );
          })}
          {notices !== null && devices.length === 0 && <p className="dash-quiet tst-none">No device yet. Turn this browser on, or open Notifications in Pinecall on your phone.</p>}
        </section>
      </div>
    </>
  );
}
