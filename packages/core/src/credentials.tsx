/** React context holding the page's credentials (gateway base and key). */

import { createContext, useContext, type ReactNode } from "react";

import type { Credentials } from "./api";

const Held = createContext<Credentials | null>(null);

/** Provide the page's credentials to the tree. */
export function CredentialsProvider({
  value,
  children,
}: {
  value: Credentials;
  children: ReactNode;
}): ReactNode {
  return <Held value={value}>{children}</Held>;
}

/** Return the page's credentials; throws when mounted without a provider. */
export function useCredentials(): Credentials {
  const held = useContext(Held);
  if (held === null) {
    throw new Error("this page was mounted without credentials");
  }
  return held;
}
