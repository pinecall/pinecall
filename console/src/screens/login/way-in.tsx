/** Layout shared by the way in — sign in, sign up, the mailed code, a password chosen: one night sky, one frosted panel. */

import type { ReactNode } from "react";

import "../../ui/ui.css";
import "./login.css";

export function WayIn({
  title,
  lede,
  children,
  aside,
  foot,
}: {
  title: string;
  lede?: ReactNode | undefined;
  children?: ReactNode | undefined;
  /** The ways out, written on the clouds under the panel. */
  aside?: ReactNode | undefined;
  foot?: ReactNode | undefined;
}): ReactNode {
  return (
    <div className="login">
      <div className="login-sky" aria-hidden />
      <div className="login-in">
        <img className="login-logo" src="/pinecall-logo-dark-966fa8a4.png" alt="Pinecall" />
        <h1 className="login-title">{title}</h1>
        {lede !== undefined && <p className="login-lede">{lede}</p>}
        {children !== undefined && <div className="login-panel">{children}</div>}
        {aside !== undefined && <p className="login-aside">{aside}</p>}
        <p className="login-foot">
          {foot ?? (
            <>
              Working from a terminal? Run <span className="login-command">pinecall login</span> on your computer, once.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
