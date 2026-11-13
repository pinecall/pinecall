/** What a right click on a call offers, in the list and in the table: open it elsewhere, copy it, judge it again, erase it. */

import type { MouseEvent } from "react";

import { isLive } from "@pinecall/core/calls";
import { useCredentials } from "@pinecall/core/credentials";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { copy, linkItems, useRowMenu } from "../ui/row-menu";
import { eraseCall, judgeAgain } from "./door";

const ON_THE_LINE = "It is on the line: end the call first";

/** `who` is the row's name, as it reads; `onErased` takes the call out of the list, which no feed frame does. */
export function useCallMenu(onErased: (call: string) => void): (event: MouseEvent<HTMLAnchorElement>, line: SessionLine, who: string) => void {
  const menu = useRowMenu();
  const credentials = useCredentials();
  return (event, line, who) => {
    const live = isLive(line);
    menu(event, [
      ...linkItems(event.currentTarget.href, who),
      { name: "Copy call id", pick: () => copy(line.call) },
      "rule",
      { name: "Judge it again", off: live ? ON_THE_LINE : undefined, pick: async () => void (await judgeAgain(credentials, line.call)) },
      "rule",
      {
        name: "Erase this call…",
        sure: "Erase for good: nothing brings it back",
        danger: true,
        off: live ? ON_THE_LINE : undefined,
        pick: async () => {
          await eraseCall(credentials, line.call);
          onErased(line.call);
        },
      },
    ]);
  };
}
