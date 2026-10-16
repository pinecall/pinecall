/** Gate that renders the box's screens for operators only. */

import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { useOrg } from "../../lib/org";

/**
 * Render nothing until whoami answers. A non-operator hitting an operator door gets a 401, which
 * would be read as a dead key and sign them out.
 */
export function OperatorOnly({ children }: { children: ReactNode }): ReactNode {
  const { operator } = useOrg();
  if (operator === null) return null;
  return operator ? children : <Navigate to="/" replace />;
}
