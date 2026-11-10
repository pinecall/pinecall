/** Which calls a status chip keeps: every call, the ones on the line, the ones waiting for a person, the ones a judge broke. */

import { isLive, wantsAPerson } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";

/** The chips, in the order they are drawn; `""` is every call. `?status=` in the address. */
export const STATUSES = [
  { value: "", name: "All" },
  { value: "live", name: "Live" },
  { value: "asking", name: "Asking" },
  { value: "broke", name: "Broke" },
] as const;

export type Status = (typeof STATUSES)[number]["value"];

/** The status the address asked for, or every call when it asked for none this page knows. */
export function statusOf(asked: string | null): Status {
  return STATUSES.find((one) => one.value === asked)?.value ?? "";
}

/** Whether a call is one this status keeps. A call nobody judged did not break: it is not in Broke. */
export function keeps(status: Status, line: SessionLine): boolean {
  switch (status) {
    case "":
      return true;
    case "live":
      return isLive(line);
    case "asking":
      return wantsAPerson(line);
    case "broke":
      return line.score?.passed === false;
  }
}
