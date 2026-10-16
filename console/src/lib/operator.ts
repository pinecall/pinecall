/** Hook that checks whether the signed-in person is a box operator. */

import { useEffect, useState } from "react";

import { doorUrl, headersFor } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "./mode";

// Uses a raw fetch, not the shared reader: there a 401 signs the person out, here it only means
// "not an operator" (runtime api/_operator.py).

/** True for an operator, false otherwise, null while loading. Always false outside production. */
export function useOperator(): boolean | null {
  const credentials = useCredentials();
  const [operator, setOperator] = useState<boolean | null>(WORLD === "production" ? null : false);

  useEffect(() => {
    if (WORLD !== "production") return undefined;
    let gone = false;
    fetch(doorUrl(credentials, "/v1/ops/whoami"), { headers: headersFor(credentials) }).then(
      (answer) => {
        if (!gone) setOperator(answer.ok);
      },
      () => {
        if (!gone) setOperator(false);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return operator;
}
