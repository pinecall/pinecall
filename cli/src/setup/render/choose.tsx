/** One question with a few answers: ↑↓ move, ⏎ takes the lit one, esc goes back. */

import { Box, Text, useInput } from "ink";
import { useState } from "react";

export interface Choice {
  value: string;
  label: string;
  hint: string;
}

export interface ChooseProps {
  title: string;
  choices: Choice[];
  initial?: string;
  onChoose: (value: string) => void;
  onBack?: () => void;
}

/** How the lit choice is drawn. */
const LIT = { color: "cyan", bold: true } as const;

export function Choose({ title, choices, initial, onChoose, onBack }: ChooseProps): React.JSX.Element {
  const [lit, setLit] = useState(Math.max(0, choices.findIndex((one) => one.value === initial)));
  useInput((_input, key) => {
    if (key.upArrow) setLit((at) => Math.max(0, at - 1));
    if (key.downArrow) setLit((at) => Math.min(choices.length - 1, at + 1));
    if (key.return && choices[lit] !== undefined) onChoose(choices[lit].value);
    if (key.escape && onBack !== undefined) onBack();
  });
  return (
    <Box flexDirection="column">
      <Text bold>{title}</Text>
      <Box flexDirection="column" marginTop={1}>
        {choices.map((one, at) => (
          <Box key={one.value}>
            <Text {...(at === lit ? LIT : {})}>{(at === lit ? "▸ " : "  ") + one.label.padEnd(16)}</Text>
            <Text dimColor>{one.hint}</Text>
          </Box>
        ))}
      </Box>
      <Box marginTop={1}>
        <Text dimColor>{onBack === undefined ? "↑↓ move · ⏎ take" : "↑↓ move · ⏎ take · esc back"}</Text>
      </Box>
    </Box>
  );
}
