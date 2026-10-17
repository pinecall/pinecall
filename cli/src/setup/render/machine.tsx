/** The machine as the runtime read it, drawn: its card or its silicon, the memory and the budget, what is here, every model measured and whether it fits. */

import { Box, Text } from "ink";

import type { Read } from "../service.js";

export function MachinePanel({ read }: { read: Read }): React.JSX.Element {
  const { machine, recommendation } = read;
  const runsOn =
    recommendation.on === "gpu"
      ? machine.cards.map((card) => `${card.name} · ${card.memory_gib} GB`).join(" + ")
      : recommendation.on === "apple"
        ? `Apple silicon · ${machine.ram_gib} GB unified`
        : `no GPU · ${machine.cores} cores · ${machine.ram_gib} GB`;
  return (
    <Box flexDirection="column">
      <Box>
        <Text bold>{"this machine  "}</Text>
        <Text>{runsOn}</Text>
        {recommendation.on !== "cpu" && <Text dimColor>{`  · ${recommendation.budget_gib} GB for the models`}</Text>}
      </Box>
      <Box>
        <Text bold>{"here          "}</Text>
        <Text>{machine.docker ? "docker ✓" : "docker ✗"}</Text>
        <Text>{machine.ollama_here ? " · ollama ✓" : " · ollama: the container"}</Text>
        <Text dimColor>{` · ${machine.system} ${machine.arch}`}</Text>
      </Box>
      <Box>
        <Text bold>{"keys set      "}</Text>
        <Text>{machine.keys_found.length === 0 ? "none" : machine.keys_found.join(", ")}</Text>
      </Box>
      <Box flexDirection="column" marginTop={1}>
        <Text bold>{"measured".padEnd(40) + "fits".padEnd(11) + "first token  message  docs  talk"}</Text>
        {recommendation.candidates.map((one) => (
          <Box key={one.model}>
            <Text>{one.model.padEnd(40)}</Text>
            <Text color={one.fits ? "green" : "red"}>{(one.fits ? "✓" : `✗ -${one.short_by_gib} GB`).padEnd(11)}</Text>
            <Text>{`${one.first_token_s}s`.padEnd(13)}</Text>
            <Text>{one.message.padEnd(9) + one.documents.padEnd(6) + one.talk}</Text>
          </Box>
        ))}
      </Box>
      {recommendation.notes.map((note) => (
        <Text key={note} color="yellow">{`! ${note}`}</Text>
      ))}
    </Box>
  );
}
