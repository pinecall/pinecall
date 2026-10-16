/** A base's markdown read as a page: headings, paragraphs, lists, quotes, tables, code, links — drawn as elements, so nothing in a file runs. */

import type { ReactNode } from "react";

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "p"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; language: string; text: string }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "rule" };

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const ITEM = /^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$/;
const FENCE = /^\s*(```|~~~)\s*([\w+#.-]*)\s*$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
// `code`, **strong**, *em* or _em_, [text](url), a bare URL — longest markers first.
const INLINE = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|(?<![\w])_([^_\n]+)_(?![\w])|\[([^\]\n]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s)<]+[^\s).,;:!?<])/g;

/** The blocks of a markdown text, read line by line. */
function blocksOf(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let at = 0;
  while (at < lines.length) {
    const line = lines[at] ?? "";
    if (line.trim() === "") {
      at += 1;
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence !== null) {
      const body: string[] = [];
      at += 1;
      while (at < lines.length && !(lines[at] ?? "").trim().startsWith(fence[1] ?? "```")) body.push(lines[at++] ?? "");
      at += 1;
      blocks.push({ kind: "code", language: fence[2] ?? "", text: body.join("\n") });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading !== null) {
      blocks.push({ kind: "heading", level: (heading[1] ?? "#").length, text: heading[2] ?? "" });
      at += 1;
      continue;
    }
    if (RULE.test(line)) {
      blocks.push({ kind: "rule" });
      at += 1;
      continue;
    }
    if (TABLE_ROW.test(line) && TABLE_RULE.test(lines[at + 1] ?? "")) {
      const cells = (row: string): string[] => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
      const head = cells(line);
      const rows: string[][] = [];
      at += 2;
      while (at < lines.length && TABLE_ROW.test(lines[at] ?? "")) rows.push(cells(lines[at++] ?? ""));
      blocks.push({ kind: "table", head, rows });
      continue;
    }
    if (line.trimStart().startsWith(">")) {
      const quoted: string[] = [];
      while (at < lines.length && (lines[at] ?? "").trimStart().startsWith(">")) quoted.push((lines[at++] ?? "").trimStart().replace(/^>\s?/, ""));
      blocks.push({ kind: "quote", text: quoted.join(" ") });
      continue;
    }
    const item = ITEM.exec(line);
    if (item !== null) {
      const ordered = item[1] !== undefined;
      const items: string[] = [];
      while (at < lines.length) {
        const next = ITEM.exec(lines[at] ?? "");
        if (next !== null && (next[1] !== undefined) === ordered) {
          items.push(next[2] ?? "");
          at += 1;
        } else if (items.length > 0 && /^\s{2,}\S/.test(lines[at] ?? "")) {
          items[items.length - 1] += ` ${(lines[at] ?? "").trim()}`;
          at += 1;
        } else break;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    const paragraph: string[] = [];
    while (at < lines.length) {
      const next = lines[at] ?? "";
      if (next.trim() === "" || HEADING.test(next) || FENCE.test(next) || ITEM.test(next) || next.trimStart().startsWith(">") || RULE.test(next)) break;
      paragraph.push(next.trim());
      at += 1;
    }
    blocks.push({ kind: "p", text: paragraph.join(" ") });
  }
  return blocks;
}

/** The inline marks of one line of text, as elements; a link opens only an http(s) address, in a new tab. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let at = 0;
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0;
    if (start > at) out.push(text.slice(at, start));
    const key = `${start}`;
    if (m[1] !== undefined) out.push(<code key={key}>{m[1]}</code>);
    else if (m[2] !== undefined || m[3] !== undefined) out.push(<strong key={key}>{m[2] ?? m[3]}</strong>);
    else if (m[4] !== undefined || m[5] !== undefined) out.push(<em key={key}>{m[4] ?? m[5]}</em>);
    else if (m[6] !== undefined && m[7] !== undefined)
      out.push(
        /^https?:\/\//i.test(m[7]) ? (
          <a key={key} href={m[7]} target="_blank" rel="noopener noreferrer">
            {m[6]}
          </a>
        ) : (
          m[6]
        ),
      );
    else if (m[8] !== undefined)
      out.push(
        <a key={key} href={m[8]} target="_blank" rel="noopener noreferrer">
          {m[8]}
        </a>,
      );
    at = start + m[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

/** A markdown file drawn as a page. */
export function MarkdownPreview({ markdown }: { markdown: string }): ReactNode {
  const blocks = blocksOf(markdown);
  if (blocks.length === 0) return <p className="md-empty">This file is empty.</p>;
  return (
    <div className="md">
      {blocks.map((block, at) => {
        switch (block.kind) {
          case "heading": {
            const Tag = `h${Math.min(block.level + 1, 6)}` as "h2";
            return <Tag key={at}>{inline(block.text)}</Tag>;
          }
          case "p":
            return <p key={at}>{inline(block.text)}</p>;
          case "list":
            return block.ordered ? (
              <ol key={at}>{block.items.map((item, n) => <li key={n}>{inline(item)}</li>)}</ol>
            ) : (
              <ul key={at}>{block.items.map((item, n) => <li key={n}>{inline(item)}</li>)}</ul>
            );
          case "quote":
            return <blockquote key={at}>{inline(block.text)}</blockquote>;
          case "code":
            return (
              <pre key={at} data-language={block.language || undefined}>
                <code>{block.text}</code>
              </pre>
            );
          case "table":
            return (
              <div key={at} className="md-table">
                <table>
                  <thead>
                    <tr>{block.head.map((cell, n) => <th key={n}>{inline(cell)}</th>)}</tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>{row.map((cell, n) => <td key={n}>{inline(cell)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "rule":
            return <hr key={at} />;
        }
      })}
    </div>
  );
}
