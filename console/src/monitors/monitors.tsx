/** Monitors, the organization's page: every monitor and every alert of this environment, and where the alerts go. */

import type { ReactNode } from "react";

import { PageHead } from "../shell/page-head";
import { MonitorsBoard } from "./board";
import { WebhookCard } from "./webhook";

export function MonitorsPage(): ReactNode {
  return (
    <>
      <PageHead />
      <div className="mon-page">
        <MonitorsBoard agent={null} />
        <WebhookCard />
      </div>
    </>
  );
}
