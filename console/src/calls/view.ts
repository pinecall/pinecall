/** The four ways a call is read. */

export type CallView = "chat" | "transcript" | "log" | "trace";

export const VIEWS: readonly { view: CallView; name: string }[] = [
  { view: "chat", name: "Chat" },
  { view: "transcript", name: "Transcript" },
  { view: "log", name: "Log" },
  { view: "trace", name: "Trace" },
];
