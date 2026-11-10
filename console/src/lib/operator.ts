/** Whether the signed-in person runs the box: true or false, null while asking. Always false outside production. */

import { useEffect, useState } from "react";

import { doorUrl, headersFor } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "./world";

// A raw fetch, not the shared reader: there a 401 signs the person out, here it only means "not an operator".
export function useOperator(): boolean | null {
  const credentials = useCredentials();
  const [operator, setOperator] = useState<boolean | null>(WORLD === "production" ? null : false);

  useEffect(() => {
    if (WORLD !== "production") return undefined;
    let gone = false;
    fetch(doorUrl(credentials, "/v1/ops/whoami"), { headers: headersFor(credentials) }).then(
      (answer) => !gone && setOperator(answer.ok),
      () => !gone && setOperator(false),
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return operator;
}
