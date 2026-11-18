/** The languages an agent's callers speak, picked by name: what the transcriber listens for, what the voice speaks, and what its calls say first. */

import { useState, type ReactNode } from "react";

import { Field } from "../ui/setting";
import { EditDialog } from "./dialog";
import { LanguageFit, LanguagesPicker, languagesIn } from "./languages";

export function LanguageEditor({ agent, initial, saving, refused, onClose, onSave }: { agent: string; initial: string; saving: boolean; refused: string | null; onClose: () => void; onSave: (languages: string) => Promise<boolean> }): ReactNode {
  const [picked, setPicked] = useState(() => languagesIn(initial));
  return (
    <EditDialog title="Language" icon="chat" about="The languages this agent's callers speak. One keeps its calls to that language; several, and a caller may speak any of them." saving={saving} refused={refused} onClose={onClose} onSave={() => void onSave(picked.join(", "))}>
      <Field label="Callers speak">
        <LanguagesPicker value={picked} onChange={setPicked} />
      </Field>
      <LanguageFit agent={agent} languages={picked} />
    </EditDialog>
  );
}
