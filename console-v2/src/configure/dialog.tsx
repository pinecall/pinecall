/** The one dialog every edit of Configure opens in: what is changed, Save and Cancel. */

import { useEffect, useRef, type FormEvent, type ReactNode } from "react";

export function EditDialog({ title, saving, refused, wide = false, onSave, onClose, children }: { title: string; saving: boolean; refused: string | null; wide?: boolean; onSave: () => void; onClose: () => void; children: ReactNode }): ReactNode {
  const held = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    held.current?.showModal();
  }, []);
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    onSave();
  };
  return (
    <dialog ref={held} className={wide ? "cfg-dialog cfg-dialog-wide" : "cfg-dialog"} onClose={onClose}>
      <form onSubmit={submit}>
        <h2 className="cfg-dialog-title">{title}</h2>
        <div className="cfg-dialog-body">{children}</div>
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}
        <div className="cfg-dialog-foot">
          <button type="button" className="app-button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="cfg-save" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
