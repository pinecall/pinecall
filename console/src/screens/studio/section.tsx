/** One section of the editor: a card with its title, a line saying what it is for, and its form. */

import type { ReactNode } from "react";

import { Card, CardHead } from "../../ui";

export function Section({ title, meta, action, children }: { title: string; meta?: string; action?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <Card>
      <CardHead title={title} meta={meta} action={action} />
      <div className="sto-body">{children}</div>
    </Card>
  );
}
