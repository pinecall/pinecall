/** Rows as aligned columns: the one table a verb prints. */

/** A table's rows, each the same number of cells; a cell is text, a number or nothing. */
export type Row = readonly (string | number | null | undefined)[];

/** The lines of a table: the header row (uppercased), then every row, columns padded to their widest cell. */
export function table(headers: readonly string[], rows: readonly Row[]): string[] {
  if (rows.length === 0) return [];
  const cells = rows.map((row) => row.map(cell));
  const widths = headers.map((header, column) => Math.max(header.length, ...cells.map((row) => row[column]?.length ?? 0)));
  const line = (row: readonly string[]): string =>
    row
      .map((text, column) => (column === row.length - 1 ? text : text.padEnd(widths[column] ?? 0)))
      .join("  ")
      .trimEnd();
  return [line(headers.map((header) => header.toUpperCase())), ...cells.map(line)];
}

/** `label  value` pairs aligned on the label, for one record's fields. */
export function fields(pairs: readonly (readonly [string, string | number | null | undefined])[]): string[] {
  const width = Math.max(0, ...pairs.map(([label]) => label.length));
  return pairs.map(([label, value]) => `${label.padEnd(width)}  ${cell(value)}`);
}

function cell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return String(value);
}
