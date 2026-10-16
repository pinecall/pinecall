/** Top bar bell: links to Notifications and prompts when this browser is not subscribed. */

import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { registerDevice } from "@pinecall/core/notify";
import { browserLabel, canBeNotified, currentSubscription, onNoticesChanged, permission, theNotifier, tokenOf } from "../lib/notifier";
import { Icon } from "../ui";

// Subscription state, re-read on change, on focus and on navigation so it never goes stale.
function useThisBrowserIsTold(): boolean | null {
  const { pathname } = useLocation();
  const credentials = useCredentials();
  const [told, setTold] = useState<boolean | null>(null);
  // Re-register the subscription on every start: the notifier may have dropped it (redeploy, a
  // token it marked dead).
  useEffect(() => {
    let gone = false;
    let registered = false;
    const look = (): void => {
      if (!canBeNotified() || permission() === "denied") return setTold(null);
      void currentSubscription().then((held) => {
        if (gone) return;
        setTold(held !== null);
        if (held === null || registered || credentials.key === "") return;
        registered = true;
        void registerDevice(theNotifier(credentials), { platform: "web", token: tokenOf(held), label: browserLabel() }).catch(() => (registered = false));
      });
    };
    look();
    const unhook = onNoticesChanged(look);
    return () => {
      gone = true;
      unhook();
    };
  }, [pathname, credentials]);
  return told;
}

// On every screen of both worlds so supervisors don't miss calls waiting for a person; each
// world's Notifications screen holds that world's choices.
export function NoticesButton(): ReactNode {
  const told = useThisBrowserIsTold();
  const navigate = useNavigate();
  const open = (): void => void navigate("/notifications");
  if (told === false) {
    return (
      <button type="button" className="top-notices top-notices-off" onClick={open}>
        <Icon name="bell" />
        Turn on notifications
      </button>
    );
  }
  return (
    <button type="button" className="top-theme" onClick={open} aria-label="Notifications" title="Notifications">
      <Icon name="bell" />
    </button>
  );
}
