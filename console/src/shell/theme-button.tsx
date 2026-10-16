/** Top bar light/dark toggle; the icon shows the theme it switches to. */

import { useSyncExternalStore, type ReactNode } from "react";

import { currentTheme, toggleTheme, watchTheme } from "@pinecall/core/theme";
import { Icon } from "../ui";

export function ThemeButton(): ReactNode {
  // Read from the document, not state: the system theme can change underneath.
  const theme = useSyncExternalStore(watchTheme, currentTheme);
  const goingTo = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="top-theme" onClick={() => toggleTheme()} aria-label={`Switch to the ${goingTo} theme`} title={`${goingTo === "dark" ? "Dark" : "Light"} theme`}>
      <Icon name={goingTo === "dark" ? "moon" : "sun"} />
    </button>
  );
}
