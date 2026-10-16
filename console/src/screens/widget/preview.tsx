/** Blank page with only the widget, minting with this key. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { loadWidget, mountWidget } from "./mount";
import "./widget.css";

export function WidgetPreview(): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const [asked] = useSearchParams();
  const [refused, setRefused] = useState<string | null>(null);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let gone = false;
    loadWidget().then(
      () => {
        if (gone || stage.current === null) return;
        const attributes: Record<string, string> = {};
        for (const key of ["name", "company", "tagline", "phone", "greeting", "theme"]) {
          const value = asked.get(key);
          if (value) attributes[key] = value;
        }
        const element = mountWidget(stage.current, credentials, agent, attributes);
        const accent = asked.get("accent");
        if (accent) element.style.setProperty("--pc-accent", accent);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, asked]);

  return (
    <div className="widget-blank">
      <div ref={stage} />
      <span className="widget-blank-mark">pinecall · {agent} · preview</span>
      {refused !== null && <p className="widget-blank-refused">{refused}</p>}
    </div>
  );
}
