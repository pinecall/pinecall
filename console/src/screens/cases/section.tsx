/** A titled part of a case's document, with a short line saying what it is for where it needs one. */

import type { ReactNode } from "react";

export function Section({ title, hint, children }: { title: string; hint?: string | undefined; children: ReactNode }): ReactNode {
  return (
    <section className="cs-sec">
      <h2 className="cs-sec-title">{title}</h2>
      {hint !== undefined && <p className="cs-sec-hint">{hint}</p>}
      {children}
    </section>
  );
}
