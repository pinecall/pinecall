/** Turn on notifications: offered in the header while this browser could be told of calls waiting for a person and is not. */

import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { registerDevice, webPushKey } from "@pinecall/core/notify";
import { browserLabel, canBeNotified, currentSubscription, noticesChanged, onNoticesChanged, permission, subscribe, theNotifier, tokenOf } from "../lib/notifier";
import { Icon } from "./icons";

export function NoticesButton(): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [told, setTold] = useState<boolean | null>(null);
  const [turning, setTurning] = useState(false);

  useEffect(() => {
    let gone = false;
    const look = (): void => {
      if (!canBeNotified() || permission() === "denied") {
        setTold(null);
        return;
      }
      void currentSubscription().then((held) => !gone && setTold(held !== null));
    };
    look();
    const unhook = onNoticesChanged(look);
    return () => {
      gone = true;
      unhook();
    };
  }, []);

  // A notifier with no key for this browser cannot subscribe here: its page says what can be done.
  const turnOn = async (): Promise<void> => {
    setTurning(true);
    try {
      const notifier = theNotifier(credentials);
      const key = await webPushKey(notifier);
      if (key === null) {
        void navigate("/notifications");
        return;
      }
      const held = await subscribe(key);
      if (held !== null) await registerDevice(notifier, { platform: "web", token: tokenOf(held), label: browserLabel() });
      noticesChanged();
    } catch {
      void navigate("/notifications");
    } finally {
      setTurning(false);
    }
  };

  if (told !== false) return null;
  return (
    <button type="button" className="sh-notices" disabled={turning} onClick={() => void turnOn()}>
      <Icon name="bell" size={15} />
      Turn on notifications
    </button>
  );
}
