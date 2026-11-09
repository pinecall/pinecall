/** A panel docked at the right of the frame, a column of its own beside the page, which stays in use: for a form, a chat, anything. */

import { useEffect, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Icon, type IconName } from "../shell/icons";
import "./ui.css";

/** The id of the frame's right column, which the shell draws empty and a panel fills. */
export const SIDE_SLOT = "side-slot";

export interface SidePanelProps {
  title: string;
  icon?: IconName | undefined;
  /** One sentence under the header. */
  about?: ReactNode;
  /** Buttons in the header, left of the close. */
  actions?: ReactNode;
  /** Pinned under the body, which scrolls alone: a Save, a chat's composer. */
  footer?: ReactNode;
  width?: number | undefined;
  /** No padding and no scroll of its own: for a body that manages both, as a chat does. */
  flush?: boolean | undefined;
  /** False for a panel Escape must not end, as a call would. */
  closesOnEscape?: boolean | undefined;
  onClose: () => void;
  children: ReactNode;
}

export function SidePanel({ title, icon, about, actions, footer, width = 472, flush = false, closesOnEscape = true, onClose, children }: SidePanelProps): ReactNode {
  useEffect(() => {
    if (!closesOnEscape) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !event.defaultPrevented) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [closesOnEscape, onClose]);
  const slot = document.getElementById(SIDE_SLOT);
  const panel = (
    <section className={slot === null ? "ui-panel ui-panel-loose" : "ui-panel"} aria-label={title} style={{ "--ui-panel-width": `${width}px` } as CSSProperties}>
      <header className="ui-panel-head">
        {icon !== undefined && (
          <span className="ui-panel-icon">
            <Icon name={icon} size={18} />
          </span>
        )}
        <h2 className="ui-panel-title">{title}</h2>
        {actions}
        <button type="button" className="ui-panel-close" aria-label="Close" onClick={onClose}>
          <Icon name="close" size={16} />
        </button>
      </header>
      <div className={flush ? "ui-panel-body ui-panel-flush" : "ui-panel-body"}>
        {about !== undefined && <p className="ui-panel-about">{about}</p>}
        {children}
      </div>
      {footer !== undefined && <footer className="ui-panel-foot">{footer}</footer>}
    </section>
  );
  // Outside the frame (no shell around it) it floats at the window's right edge instead.
  return createPortal(panel, slot ?? document.body);
}
