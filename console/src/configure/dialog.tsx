/** The one panel every edit of Configure opens in: what is changed, Save and Cancel. */

import { useId, type FormEvent, type ReactNode } from "react";

import type { IconName } from "../shell/icons";
import { SidePanel } from "../ui/side-panel";

export function EditDialog({ title, icon, about, saving, refused, onSave, onClose, children }: { title: string; icon?: IconName | undefined; about?: ReactNode; saving: boolean; refused: string | null; onSave: () => void; onClose: () => void; children: ReactNode }): ReactNode {
  const form = useId();
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    onSave();
  };
  return (
    <SidePanel
      title={title}
      icon={icon}
      about={about}
      onClose={onClose}
      footer={
        <>
          {refused !== null && (
            <p className="cfg-refused" role="alert">
              {refused}
            </p>
          )}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form={form} className="cfg-save" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </>
      }
    >
      <form id={form} className="cfg-dialog-body" onSubmit={submit}>
        {children}
      </form>
    </SidePanel>
  );
}
