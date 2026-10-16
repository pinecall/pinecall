/** Syntax colour for the guide's code, by a small tokenizer: comments, strings, decorators, keywords, types and numbers. */

import type { ReactNode } from "react";

import type { Language } from "./agent-code";

/** The token kinds, each a class of the panel. Order matters: the first alternative that matches wins. */
const KINDS = ["comment", "string", "decorator", "keyword", "type", "number"] as const;
type Kind = (typeof KINDS)[number];

const KEYWORDS: Record<Language, string> = {
  typescript: "import|from|export|default|class|extends|async|await|return|override|const|let|this|type|new",
  ruby: "require|class|def|end|self|tool|stage|state|frozen_string_literal|true|false|nil",
  python: "from|import|class|def|return|self|None|True|False",
};

const COMMENT: Record<Language, string> = {
  typescript: "\\/\\*[\\s\\S]*?\\*\\/|\\/\\/[^\\n]*",
  ruby: "#[^\\n]*",
  python: '"""[\\s\\S]*?"""|#[^\\n]*',
};

const STRING: Record<Language, string> = {
  typescript: '"(?:[^"\\\\]|\\\\.)*"|\'(?:[^\'\\\\]|\\\\.)*\'|`(?:[^`\\\\]|\\\\.)*`',
  ruby: '"(?:[^"\\\\]|\\\\.)*"|:[a-z_]+|%i\\[[^\\]]*\\]',
  python: '"(?:[^"\\\\]|\\\\.)*"|\'(?:[^\'\\\\]|\\\\.)*\'',
};

function grammar(language: Language): RegExp {
  const parts = [COMMENT[language], STRING[language], "@\\w+", `\\b(?:${KEYWORDS[language]})\\b`, "\\b[A-Z]\\w*\\b", "\\b\\d+\\b"];
  return new RegExp(parts.map((part) => `(${part})`).join("|"), "g");
}

/** The code as spans, each token in its kind's class, the rest as it is. */
export function highlighted(code: string, language: Language): ReactNode[] {
  const out: ReactNode[] = [];
  let at = 0;
  for (const found of code.matchAll(grammar(language))) {
    const index = found.index ?? 0;
    if (index > at) out.push(code.slice(at, index));
    const kind: Kind = KINDS[found.slice(1).findIndex((group) => group !== undefined)] ?? "number";
    out.push(
      <span key={index} className={`wel-tok-${kind}`}>
        {found[0]}
      </span>,
    );
    at = index + found[0].length;
  }
  if (at < code.length) out.push(code.slice(at));
  return out;
}
