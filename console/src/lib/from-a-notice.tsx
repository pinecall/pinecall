/** Switch to the org named in a notification link before opening the call. */

import { useEffect, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import { useWhoami } from "./whoami";
import { useWorld } from "./world";

// The service worker opens `/calls/<call>?org=<org>` (public/sw.js). A key only reads its own org's
// calls, so switch orgs first; if already there, just drop the query param.
export function FromANotice(): ReactNode {
  const whose = useWhoami();
  const { moveTo } = useWorld();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const org = new URLSearchParams(search).get("org");

  useEffect(() => {
    if (org === null || whose === null) return;
    if (org === whose.org) void navigate(pathname, { replace: true });
    else void moveTo(org, pathname).catch(() => navigate(pathname, { replace: true }));
  }, [org, whose, pathname, moveTo, navigate]);

  return null;
}
