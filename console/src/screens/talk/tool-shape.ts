/** A tool's answer read as what it means, for any agent: a list as chips or rows, a record as a receipt, long text as code — or nothing, and its card shows it raw. */

/** What a tool's output is drawn as. */
export type Shape =
  | { kind: "chips"; items: string[]; more: number }
  | { kind: "rows"; items: { head: string; rest: string }[]; more: number }
  | { kind: "receipt"; fields: { name: string; value: string }[] }
  | { kind: "code"; text: string };

// The field a person reads an item by, first found wins; else the item's first short text.
const READABLE = ["name", "title", "label", "when", "time", "slot", "date", "start", "starts_at", "startsAt", "text", "value", "summary", "description", "email", "phone"];

// A chip holds a few words; a longer one, or an item that says more than its name, is a row.
const CHIP_CHARS = 28;
// The most items a card draws; the rest are counted.
const MOST_ITEMS = 12;
// A record with more fields than a receipt holds is read raw.
const RECEIPT_FIELDS = 8;
// Text this long, or of more than one line, is drawn as code.
const LONG_TEXT = 160;
// What a row says beside its name: its next fields, a few.
const ROW_FIELDS = 2;

type Fields = Record<string, unknown>;
type Scalar = string | number | boolean | null;

/** The shape a tool's output is drawn as, or null when it is none of them. */
export function shapeOf(output: unknown): Shape | null {
  const value = decoded(output);
  if (typeof value === "string") return value.length >= LONG_TEXT || value.includes("\n") ? { kind: "code", text: value } : null;
  if (Array.isArray(value)) return listOf(value);
  if (isRecord(value)) return receiptOf(value);
  return null;
}

// An app that answers JSON as a string answered a value: it is read as the value.
function decoded(output: unknown): unknown {
  if (typeof output !== "string" || !/^\s*[[{]/.test(output)) return output;
  try {
    return JSON.parse(output) as unknown;
  } catch {
    return output;
  }
}

function listOf(items: unknown[]): Shape | null {
  if (items.length === 0) return null;
  const read = items.map(itemOf);
  if (read.some((item) => item === null)) return null;
  const rows = read as { head: string; rest: string }[];
  const shown = rows.slice(0, MOST_ITEMS);
  const more = rows.length - shown.length;
  if (shown.every((row) => row.rest === "" && row.head.length <= CHIP_CHARS)) return { kind: "chips", items: shown.map((row) => row.head), more };
  return { kind: "rows", items: shown, more };
}

// One item of a list: a scalar is its own name; a record is named by its most readable field, and
// its next few short fields say the rest. An item with nothing to read it by makes the list raw.
function itemOf(item: unknown): { head: string; rest: string } | null {
  if (isScalar(item)) return item === null ? null : { head: String(item), rest: "" };
  if (!isRecord(item)) return null;
  const texts = Object.entries(item).filter((entry): entry is [string, Scalar] => isScalar(entry[1]) && entry[1] !== null && String(entry[1]).trim() !== "" && !isAnId(entry[0]));
  const named = READABLE.map((name) => texts.find(([key]) => key === name)).find((found) => found !== undefined) ?? texts.find(([, value]) => typeof value === "string");
  if (named === undefined) return null;
  const rest = texts
    .filter(([key, value]) => key !== named[0] && typeof value === "string" && value.length <= CHIP_CHARS * 2 && !looksLikeATimestamp(value))
    .slice(0, ROW_FIELDS)
    .map(([, value]) => String(value));
  return { head: String(named[1]), rest: rest.join(" · ") };
}

function receiptOf(record: Fields): Shape | null {
  const entries = Object.entries(record);
  if (entries.length === 0 || entries.length > RECEIPT_FIELDS || !entries.every(([, value]) => isScalar(value))) return null;
  return { kind: "receipt", fields: entries.map(([name, value]) => ({ name: spoken(name), value: shown(value as Scalar) })) };
}

/** `startsAt`, `starts_at` → `starts at`. */
function spoken(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .toLowerCase();
}

function shown(value: Scalar): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

// An id names an item to the app, not to a person: never what a row is read by.
function isAnId(key: string): boolean {
  return key === "id" || /(_id|Id)$/.test(key);
}

function looksLikeATimestamp(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value);
}

function isScalar(value: unknown): value is Scalar {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function isRecord(value: unknown): value is Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
