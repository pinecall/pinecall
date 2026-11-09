/** A select drawn by us: rich rows, groups, a search, the keyboard; it opens over whatever scrolls around it. */

import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";

import { Icon } from "../shell/icons";
import "./ui.css";

export interface SelectItem {
  value: string;
  label: string;
  /** The line under the label. */
  detail?: ReactNode;
  leading?: ReactNode;
  /** Small badges on the right of the row. */
  tags?: ReactNode;
  /** Something the row does besides being picked: its clicks do not pick it. */
  trailing?: ReactNode;
  disabled?: boolean | undefined;
  hint?: string | undefined;
  /** A heading drawn above the first row of each run of rows that share it. */
  group?: string | undefined;
  /** What the search reads beside the label. */
  keywords?: string | undefined;
}

export interface SelectProps {
  items: readonly SelectItem[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string | undefined;
  /** Unsaid: a search appears from nine rows. */
  searchable?: boolean | undefined;
  searchPlaceholder?: string | undefined;
  /** Drawn above the rows: filters of the caller's own. */
  head?: ReactNode;
  /** The most rows drawn at once; the search reaches the others. */
  limit?: number | undefined;
  disabled?: boolean | undefined;
}

const LONGEST_MENU = 380;
const WANTS_BELOW = 240;
const FROM_THE_EDGE = 12;

export function Select({ items, value, onChange, label, placeholder = "Choose…", searchable, searchPlaceholder = "Search", head, limit, disabled = false }: SelectProps): ReactNode {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<CSSProperties>({});
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const activeRow = useRef<HTMLDivElement>(null);
  const picked = items.find((one) => one.value === value);
  const withSearch = searchable ?? items.length > 8;

  const shown = useMemo(() => {
    const typed = query.trim().toLowerCase();
    const found = typed === "" ? items : items.filter((one) => `${one.label} ${one.keywords ?? ""}`.toLowerCase().includes(typed));
    return limit === undefined ? found : found.slice(0, limit);
  }, [items, query, limit]);

  const close = (): void => {
    setOpen(false);
    setQuery("");
  };

  const show = (): void => {
    const box = trigger.current?.getBoundingClientRect();
    if (box === undefined) return;
    const below = window.innerHeight - box.bottom - FROM_THE_EDGE;
    const above = box.top - FROM_THE_EDGE;
    const up = below < WANTS_BELOW && above > below;
    setPlace({ left: box.left, width: box.width, maxHeight: Math.min(LONGEST_MENU, up ? above : below), ...(up ? { bottom: window.innerHeight - box.top + 6 } : { top: box.bottom + 6 }) });
    setActive(Math.max(0, items.findIndex((one) => one.value === value)));
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    (withSearch ? search.current : menu.current)?.focus();
    const outside = (event: MouseEvent): void => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    // Its place was measured once: whatever moves the trigger closes it, but its own list scrolling.
    const moved = (event: Event): void => {
      if (!menu.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("mousedown", outside);
    window.addEventListener("scroll", moved, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", outside);
      window.removeEventListener("scroll", moved, true);
      window.removeEventListener("resize", close);
    };
  }, [open, withSearch]);

  useEffect(() => {
    activeRow.current?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const pick = (item: SelectItem): void => {
    if (item.disabled === true) return;
    onChange(item.value);
    close();
    trigger.current?.focus();
  };

  const step = (by: 1 | -1): void => {
    for (let at = active + by; at >= 0 && at < shown.length; at += by) {
      if (shown[at]?.disabled !== true) return setActive(at);
    }
  };

  const onKey = (event: KeyboardEvent): void => {
    if (event.key === "Tab") return close();
    if (!["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) return;
    // Enter would send the form around it, Escape would close the panel around it.
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "ArrowDown") step(1);
    else if (event.key === "ArrowUp") step(-1);
    else if (event.key === "Escape") {
      close();
      trigger.current?.focus();
    } else {
      const item = shown[active];
      if (item !== undefined) pick(item);
    }
  };

  let lastGroup: string | undefined;
  return (
    <div ref={root} className="ui-select">
      <button
        ref={trigger}
        type="button"
        className="ui-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
            event.preventDefault();
            show();
          }
        }}
      >
        {picked?.leading}
        <span className="ui-select-words">
          <span className={picked === undefined ? "ui-clip ui-quiet" : "ui-clip"}>{picked?.label ?? placeholder}</span>
          {picked?.detail !== undefined && picked.detail !== "" && <span className="ui-select-detail ui-clip">{picked.detail}</span>}
        </span>
        <span className="ui-select-chevron">
          <Icon name="chevron" size={15} />
        </span>
      </button>
      {open && (
        <div ref={menu} className="ui-select-menu" style={place} tabIndex={-1} onKeyDown={onKey}>
          {withSearch && (
            <div className="ui-select-search">
              <Icon name="search" size={14} />
              <input
                ref={search}
                aria-label={searchPlaceholder}
                placeholder={searchPlaceholder}
                spellCheck={false}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setActive(0);
                }}
              />
            </div>
          )}
          {head}
          <div className="ui-select-rows" role="listbox" aria-label={label}>
            {shown.length === 0 && <p className="ui-select-none">Nothing by that name.</p>}
            {shown.map((item, at) => {
              const heading = item.group !== undefined && item.group !== lastGroup ? item.group : null;
              lastGroup = item.group;
              const classes = ["ui-select-row", at === active ? "ui-select-active" : "", item.disabled === true ? "ui-select-off" : ""].join(" ");
              return (
                <div key={item.value} role="presentation">
                  {heading !== null && <div className="ui-select-group">{heading}</div>}
                  <div ref={at === active ? activeRow : undefined} role="option" aria-selected={item.value === value} aria-disabled={item.disabled === true} title={item.hint} className={classes} onMouseEnter={() => setActive(at)} onClick={() => pick(item)}>
                    {item.leading}
                    <span className="ui-select-words">
                      <span className="ui-clip">{item.label}</span>
                      {item.detail !== undefined && item.detail !== "" && <span className="ui-select-detail ui-clip">{item.detail}</span>}
                    </span>
                    {item.tags}
                    {item.trailing !== undefined && (
                      <span className="ui-select-trailing" onClick={(event) => event.stopPropagation()}>
                        {item.trailing}
                      </span>
                    )}
                    {item.value === value && (
                      <span className="ui-select-check">
                        <Icon name="check" size={15} />
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
