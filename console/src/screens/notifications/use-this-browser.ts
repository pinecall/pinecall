/** Hook for this browser's push support, subscription state and renewal. */

import { useCallback, useEffect, useState } from "react";

import type { Credentials } from "@pinecall/core/api";
import { registerDevice, unregisterDevice, webPushKey } from "@pinecall/core/notify";
import {
  browserLabel,
  canBeNotified,
  currentSubscription,
  noticesChanged,
  permission,
  subscribe,
  theNotifier,
  tokenOf,
} from "../../lib/notifier";

export type Standing = "unsupported" | "blocked" | "off" | "on" | "unknown";

export interface ThisBrowser {
  standing: Standing;
  /** Notifier device id once registered; targeted by a test notification. */
  deviceId: string | null;
  turnOn: () => Promise<void>;
  turnOff: () => Promise<void>;
  /** Resubscribe after the push service dropped this browser's subscription. */
  renew: () => Promise<void>;
}

export function useThisBrowser(credentials: Credentials): ThisBrowser {
  const [standing, setStanding] = useState<Standing>("unknown");
  const [deviceId, setDeviceId] = useState<string | null>(null);

  // Re-register an existing subscription under this org, so one subscription serves every org.
  useEffect(() => {
    let gone = false;
    void (async () => {
      if (!canBeNotified()) return setStanding("unsupported");
      if (permission() === "denied") return setStanding("blocked");
      const held = await currentSubscription();
      if (held !== null) {
        const id = await registerDevice(theNotifier(credentials), { platform: "web", token: tokenOf(held), label: browserLabel() });
        if (!gone) setDeviceId(id);
      }
      if (!gone) setStanding(held === null ? "off" : "on");
    })();
    return () => {
      gone = true;
    };
  }, [credentials]);

  const take = useCallback(
    async (anew: boolean): Promise<void> => {
      const notifier = theNotifier(credentials);
      const key = await webPushKey(notifier);
      if (key === null) throw new Error("The notifier has no key for browsers yet.");
      const subscription = await subscribe(key, { anew });
      if (subscription === null) {
        setStanding(permission() === "denied" ? "blocked" : "off");
        noticesChanged();
        return;
      }
      setDeviceId(await registerDevice(notifier, { platform: "web", token: tokenOf(subscription), label: browserLabel() }));
      setStanding("on");
      noticesChanged();
    },
    [credentials],
  );

  const turnOn = useCallback(() => take(false), [take]);
  const renew = useCallback(() => take(true), [take]);

  const turnOff = useCallback(async (): Promise<void> => {
    const subscription = await currentSubscription();
    if (subscription !== null) {
      await unregisterDevice(theNotifier(credentials), { platform: "web", token: tokenOf(subscription) });
      await subscription.unsubscribe();
    }
    setDeviceId(null);
    setStanding("off");
    noticesChanged();
  }, [credentials]);

  return { standing, deviceId, turnOn, turnOff, renew };
}
