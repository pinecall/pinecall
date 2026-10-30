// The hold melody as a class writes it: a file beside the class, the seconds of quiet before it, or silence.

/** `static hold = { file: "hold.mp3", afterS: 1.5 }`, `{ afterS }`, `{ off: true }`, or `"off"`. */
export interface HoldDeclaration {
  /** The file, relative to the class's own; absent, the runtime's melody. */
  file?: string;
  /** Seconds of the agent's quiet before the melody starts, 0 to 30; absent, the runtime's. */
  afterS?: number;
  /** True plays nothing while a tool runs. */
  off?: boolean;
}
