/** The theme switcher: one icon in the header that turns the console light or dark. */

import { useEffect, useState, type ReactNode } from "react";

import { chooseTheme, currentTheme, watchTheme } from "@pinecall/core/theme";
import { Icon } from "./icons";

export function ThemeButton(): ReactNode {
  const [theme, setTheme] = useState(currentTheme);

  useEffect(() => watchTheme(() => setTheme(currentTheme())), []);

  const other = theme === "dark" ? "Light theme" : "Dark theme";
  return (
    <button type="button" className="sh-notices" aria-label={other} title={other} onClick={() => setTheme(chooseTheme(theme === "dark" ? "light" : "dark"))}>
      <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
    </button>
  );
}
