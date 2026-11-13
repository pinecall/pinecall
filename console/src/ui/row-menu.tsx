/** The menu a right click opens on a row of any list: what can be done with it, at the pointer. */

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import "./ui.css";

export interface MenuAction {
  name: string;
  /** Done when picked; a promise that rejects is said under the page. */
  pick: () => void | Promise<void>;
  /** Asked first: the item turns into these words, and a second pick does it. */
  sure?: string;
  danger?: boolean;
  /** Why it cannot be picked now: the item is drawn, and off. */
  off?: string | undefined;
}

/** An action, or the rule between two groups of them. */
export type MenuItem = MenuAction | "rule";

/** Where it was asked for: a right click, the menu key, or anything with a place on screen. */
export interface Asked {
  clientX: number;
  clientY: number;
  preventDefault: () => void;
}

type Opening = (asked: Asked, items: readonly MenuItem[]) => void;

const Menus = createContext<Opening>(() => undefined);

/** Open the menu: `onContextMenu={(event) => menu(event, items)}` on a row. */
export function useRowMenu(): Opening {
  return useContext(Menus);
}

/** Onto the clipboard; refused, the menu says why under the page. */
export async function copy(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

/** What any row that is a link can do: open beside this tab, and be copied by its address or its name. */
export function linkItems(href: string, name: string): MenuItem[] {
  return [
    { name: "Open in a new tab", pick: () => void window.open(href, "_blank", "noopener") },
    { name: "Copy link", pick: () => copy(href) },
    ...(name === "" ? [] : [{ name: `Copy “${name.length > 28 ? `${name.slice(0, 27)}…` : name}”`, pick: () => copy(name) }]),
  ];
}

// A row's name is the first thing its top line says; a row with no top line is named by all it says.
function nameOf(row: HTMLAnchorElement): string {
  const top = row.querySelector(".app-row-top");
  return ((top?.firstElementChild ?? top ?? row).textContent ?? "").trim();
}

const A_ROW = "a.app-row, a.dash-row";
const SAID_FOR_MS = 5000;
const EDGE = 8;

interface Open {
  x: number;
  y: number;
  items: readonly MenuItem[];
}

/**
 * Every list's rows get a menu from this one place: a row that names its own actions opens it itself
 * (`useRowMenu`), and any other row that is a link gets what a link can do.
 */
export function RowMenus({ children }: { children: ReactNode }): ReactNode {
  const [menu, setMenu] = useState<Open | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const open = useCallback<Opening>((asked, items) => {
    if (items.length === 0) return;
    asked.preventDefault();
    setMenu({ x: asked.clientX, y: asked.clientY, items });
  }, []);

  useEffect(() => {
    const onMenu = (event: MouseEvent): void => {
      if (event.defaultPrevented || !(event.target instanceof Element)) return;
      const row = event.target.closest(A_ROW);
      if (row instanceof HTMLAnchorElement) open(event, linkItems(row.href, nameOf(row)));
    };
    document.addEventListener("contextmenu", onMenu);
    return () => document.removeEventListener("contextmenu", onMenu);
  }, [open]);

  useEffect(() => {
    if (said === null) return undefined;
    const gone = window.setTimeout(() => setSaid(null), SAID_FOR_MS);
    return () => window.clearTimeout(gone);
  }, [said]);

  const close = useCallback((): void => setMenu(null), []);
  const failed = useCallback((why: unknown): void => setSaid(why instanceof Error ? why.message : String(why)), []);

  return (
    <Menus.Provider value={open}>
      {children}
      {menu !== null && createPortal(<TheMenu key={`${menu.x}:${menu.y}`} menu={menu} onClose={close} onFailed={failed} />, document.body)}
      {said !== null &&
        createPortal(
          <div className="ui-said" role="alert">
            {said}
          </div>,
          document.body,
        )}
    </Menus.Provider>
  );
}

function TheMenu({ menu, onClose, onFailed }: { menu: Open; onClose: () => void; onFailed: (why: unknown) => void }): ReactNode {
  const box = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState({ left: menu.x, top: menu.y });
  // The item asked "are you sure" of: its second pick does it.
  const [armed, setArmed] = useState<number | null>(null);

  // Kept inside the window: a menu asked for at the bottom edge opens upwards.
  useLayoutEffect(() => {
    const size = box.current?.getBoundingClientRect();
    if (size === undefined) return;
    setAt({
      left: Math.max(EDGE, Math.min(menu.x, window.innerWidth - size.width - EDGE)),
      top: Math.max(EDGE, Math.min(menu.y, window.innerHeight - size.height - EDGE)),
    });
    box.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, [menu]);

  useEffect(() => {
    const away = (event: Event): void => {
      if (event.target instanceof Node && box.current?.contains(event.target)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") return onClose();
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Home" && event.key !== "End") return;
      event.preventDefault();
      const all = [...(box.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
      const here = all.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? all.length - 1 : (here + (event.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
      all[next]?.focus();
    };
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onClose, true);
    window.addEventListener("resize", onClose);
    window.addEventListener("blur", onClose);
    return () => {
      document.removeEventListener("pointerdown", away, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onClose, true);
      window.removeEventListener("resize", onClose);
      window.removeEventListener("blur", onClose);
    };
  }, [onClose]);

  const pick = (item: MenuAction, index: number): void => {
    if (item.sure !== undefined && armed !== index) return setArmed(index);
    onClose();
    void Promise.resolve()
      .then(() => item.pick())
      .catch(onFailed);
  };

  return (
    <div ref={box} className="ui-menu" role="menu" style={at} onContextMenu={(event) => event.preventDefault()}>
      {menu.items.map((item, index) =>
        item === "rule" ? (
          <div key={index} className="ui-menu-rule" role="separator" />
        ) : (
          <button
            key={index}
            type="button"
            role="menuitem"
            className={item.danger === true || armed === index ? "ui-menu-item ui-menu-item-bad" : "ui-menu-item"}
            disabled={item.off !== undefined}
            title={item.off}
            onClick={() => pick(item, index)}
          >
            {armed === index ? item.sure : item.name}
          </button>
        ),
      )}
    </div>
  );
}
