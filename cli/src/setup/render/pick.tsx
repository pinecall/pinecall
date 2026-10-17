/** One stage's picker: a line typed into, the options that match it listed under, arrows to move, enter to take one or what was typed. */

import { Box, Text, useInput } from "ink";
import TextInput from "ink-text-input";
import { useState } from "react";

import type { Option } from "../service.js";

/** How many options are shown under the line at once. */
const ROWS = 8;
/** How the lit option is drawn. */
const LIT = { color: "cyan", bold: true } as const;

export interface PickProps {
  title: string;
  /** What the stage decides, in one line under the title. */
  about: string;
  options: Option[];
  initial: string;
  /** Whether a value none of the options has may be typed (an Ollama tag the table never measured). */
  freeText: boolean;
  onPick: (value: string) => void;
  onBack: () => void;
}

/** The picker: typing narrows the list, ↑↓ move, ⏎ takes the lit one or the text itself, esc goes back. */
export function Pick({ title, about, options, initial, freeText, onPick, onBack }: PickProps): React.JSX.Element {
  const [typed, setTyped] = useState(initial);
  const [lit, setLit] = useState(Math.max(0, options.findIndex((one) => one.value === initial)));
  const shown = matching(options, typed);
  const chosen = shown[Math.min(lit, Math.max(0, shown.length - 1))];
  useInput((_input, key) => {
    if (key.escape) onBack();
    if (key.upArrow) setLit((at) => Math.max(0, Math.min(at, shown.length - 1) - 1));
    if (key.downArrow) setLit((at) => Math.min(shown.length - 1, at + 1));
  });
  const submit = (text: string): void => {
    const exact = shown.find((one) => one.value === text.trim());
    if (exact !== undefined) return onPick(exact.value);
    if (chosen !== undefined && text.trim() === "") return onPick(chosen.value);
    if (freeText && text.trim() !== "") return onPick(text.trim());
    if (chosen !== undefined) onPick(chosen.value);
  };
  return (
    <Box flexDirection="column">
      <Text bold>{title}</Text>
      <Text dimColor>{about}</Text>
      <Box marginTop={1}>
        <Text color="cyan">{"› "}</Text>
        <TextInput value={typed} onChange={(text) => { setTyped(text); setLit(0); }} onSubmit={submit} />
      </Box>
      <Box flexDirection="column" marginTop={1}>
        {shown.slice(0, ROWS).map((one, at) => (
          <Box key={one.value}>
            <Text {...(one === chosen ? LIT : {})}>{(one === chosen ? "▸ " : "  ") + one.value.padEnd(44)}</Text>
            <Text color={one.fits === false ? "red" : "green"}>{one.fits === undefined ? "  " : one.fits ? "✓ " : "✗ "}</Text>
            <Text dimColor>{one.hint}</Text>
          </Box>
        ))}
        {shown.length > ROWS && <Text dimColor>{`  … ${shown.length - ROWS} more: keep typing`}</Text>}
        {shown.length === 0 && (
          <Text dimColor>{freeText ? "nothing measured by that name: ⏎ takes what you typed as an Ollama tag" : "nothing by that name"}</Text>
        )}
      </Box>
      <Box marginTop={1}>
        <Text dimColor>{"↑↓ move · ⏎ take · type to narrow · esc back"}</Text>
      </Box>
    </Box>
  );
}

function matching(options: Option[], typed: string): Option[] {
  const needle = typed.trim().toLowerCase();
  if (needle === "") return options;
  return options.filter((one) => one.value.toLowerCase().includes(needle) || one.hint.toLowerCase().includes(needle));
}
