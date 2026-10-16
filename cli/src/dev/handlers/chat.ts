/** The console's Chat screen: written calls against the agent this process serves, so a tool's breakpoint works from the terminal. */

import { DevRefused } from "@pinecall/agents/client";
import { z } from "zod";

import { chatLine } from "../../calls/render.js";
import { Chat } from "../../calls/service/chat.js";
import { goldensInFolder } from "../../evals/service/goldens.js";
import { mine, type Here, type Screen } from "./screen.js";

const StartChat = z.object({ agent: z.string().min(1), as: z.string().min(1).optional(), golden: z.string().min(1).optional() });
const Say = z.object({ call: z.string().min(1), text: z.string().min(1) });
const End = z.object({ call: z.string().min(1) });

/** Chat for one agent: its roster (the goldens that declare a state to open in), and the calls this console opened. */
export function chatHandlers(here: Here): Screen {
  const open = new Map<string, Chat>();
  const held = (call: string): Chat => {
    const chat = open.get(call);
    if (chat === undefined) throw new DevRefused(404, `${call} is not a chat this console opened`);
    return chat;
  };
  const states = async (): Promise<{ name: string; state: Record<string, unknown> }[]> =>
    (await goldensInFolder(here.home.goldens)).filter((golden) => golden.state !== undefined).map((golden) => ({ name: golden.name, state: golden.state! }));
  return {
    verbs: {
      "chat.roster": async () => ({ agent: here.home.name, states: (await states()).map((one) => one.name) }),
      "chat.start": async (asked) => {
        const wanted = StartChat.parse(asked);
        mine(here, wanted.agent, "chat with");
        const state = wanted.golden === undefined ? undefined : (await states()).find((one) => one.name === wanted.golden)?.state;
        if (wanted.golden !== undefined && state === undefined) throw new DevRefused(404, `no golden called ${wanted.golden} declares a state to open a call in`);
        // Naming the app routes the call to this process, not to the newest holder; read on every dial.
        const chat = await Chat.open(here.ctx, { agent: here.home.name, app: () => here.served.app(), contact: wanted.as, state }, {
          onEntry: (entry) => {
            const line = chatLine(entry);
            if (line !== null) here.ctx.io.print(line);
          },
        });
        open.set(chat.call!, chat);
        return { call: chat.call };
      },
      "chat.say": async (asked) => {
        const { call, text } = Say.parse(asked);
        held(call).say(text);
        return { call };
      },
      "chat.end": async (asked) => {
        const { call } = End.parse(asked);
        const chat = held(call);
        open.delete(call);
        void chat.end();
        return { call };
      },
    },
    close: async () => {
      await Promise.allSettled([...open.values()].map((chat) => chat.end()));
      open.clear();
    },
  };
}
