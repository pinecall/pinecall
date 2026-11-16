/** Colour for a terminal: one line read for what it is (a title, a table's header, a label, a mark, a turn) and painted. */

// The renderers write plain text in a few shapes, the same in every domain; colour is said here alone,
// from the shape, so a pipe, a file and a test read the text a renderer wrote and nothing else.

const ESC = "\u001b[";
const PLAIN = `${ESC}0m`;

const tint =
  (code: string) =>
  (text: string): string =>
    text === "" ? "" : `${ESC}${code}m${text}${PLAIN}`;

const green = tint("32");
const red = tint("31");
const yellow = tint("33");
const magenta = tint("35");
const cyan = tint("36");
const dim = tint("2");
const bold = tint("1");
// Pinecall's violet, in the 256 colours every terminal has.
const accent = tint("1;38;5;141");

const DOT = " · ";

/** What a cell that is one of these words alone is painted with: a standing, an environment, nothing there. */
const WORDS: Readonly<Record<string, (text: string) => string>> = {
  ready: green,
  live: green,
  active: green,
  running: green,
  passed: green,
  held: green,
  on: green,
  stopped: yellow,
  pending: yellow,
  draining: yellow,
  sandbox: yellow,
  production: magenta,
  failed: red,
  refused: red,
  broke: red,
  off: dim,
  no: dim,
  "—": dim,
  "-": dim,
  "nothing set": dim,
};

/** One line painted for a terminal; a line that carries colour of its own is left as it is. */
export function paintLine(line: string): string {
  if (line === "" || line.includes(ESC)) return line;
  for (const rule of RULES) {
    const painted = rule(line);
    if (painted !== undefined) return painted;
  }
  return cells(line);
}

type Rule = (line: string) => string | undefined;

// `dental-billing │ …`: a line of one agent among several, as `start` prefixes them.
const ofAnAgent: Rule = (line) => {
  const found = /^(\S+ *│ )(.*)$/.exec(line);
  return found === null ? undefined : `${dim(found[1] ?? "")}${paintLine(found[2] ?? "")}`;
};

const refusal: Rule = (line) => (line.startsWith("pinecall: ") ? `${tint("1;31")("pinecall:")}${line.slice("pinecall:".length)}` : undefined);

// Two spaces: a tool call in a transcript opens with → too, at the line's start.
const nextStep: Rule = (line) => {
  const found = /^( {2,})([→–]) (.*)$/.exec(line);
  if (found === null) return undefined;
  const [, lead = "", glyph = "", rest = ""] = found;
  return glyph === "→" ? `${lead}${cyan(glyph)} ${dim(rest)}` : dim(line);
};

const mark: Rule = (line) => {
  const found = /^(\s*)([✓✗])( .*|$)/.exec(line);
  if (found === null) return undefined;
  const [, lead = "", glyph = "", rest = ""] = found;
  return `${lead}${glyph === "✓" ? green(glyph) : red(glyph)}${dots(rest)}`;
};

// A transcript: what the agent said, what the caller said, a tool asked and its answer.
const turn: Rule = (line) => {
  const said = /^(\s*)([›‹]) (.*)$/.exec(line);
  if (said !== null) {
    const [, lead = "", glyph = "", rest = ""] = said;
    return glyph === "›" ? `${lead}${accent(glyph)} ${rest}` : `${lead}${cyan(glyph)} ${dim(rest)}`;
  }
  const called = /^→ ([\w.-]+)(.*)$/.exec(line);
  if (called !== null) return `${yellow(`→ ${called[1] ?? ""}`)}${dim(called[2] ?? "")}`;
  const answered = /^← ([\w.-]+)(.*)$/.exec(line);
  if (answered !== null) return `${dim("←")} ${yellow(answered[1] ?? "")}${dim(answered[2] ?? "")}`;
  return undefined;
};

// `── identity (static) ──`, and a tag of the prompt alone on its line.
const section: Rule = (line) => {
  if (line.startsWith("── ")) return cyan(line);
  return /^<\/?[a-z_-]+>$/.test(line) ? dim(line) : undefined;
};

// The help, as commander lays it out: `Usage: …`, then `Options:` and `Commands:` over their rows.
const help: Rule = (line) => {
  if (line.startsWith("Usage: ")) return `${bold("Usage:")}${line.slice("Usage:".length)}`;
  return /^[A-Z][a-z]+(?: [a-z]+)*:$/.test(line) ? bold(line) : undefined;
};

// A table's header is its columns in capitals; the columns over a record's corners sit indented past its labels.
const header: Rule = (line) => {
  if (/^[A-Z][A-Z0-9 ]*[A-Z0-9]$/.test(line)) return bold(line);
  return /^ {10,}\S+(?: {2,}\S+)+$/.test(line) ? bold(line) : undefined;
};

// `clinica-norte · sandbox · 3 cases`: what the answer is about, then what there is to say of it.
const title: Rule = (line) => {
  if (line.startsWith(" ") || !line.includes(DOT) || / {2,}/.test(line)) return undefined;
  const [first = "", ...rest] = line.split(DOT);
  const named = /^\S+$/.test(first) && !/^\d/.test(first) ? accent(first) : cell(first);
  return [named, ...rest.map((one) => (/^[\d.,]+ ?m?s$/.test(one) ? dim(one) : cell(one)))].join(dim(DOT));
};

// `  key   k_abc`: a record's field, its label and then what it holds.
const field: Rule = (line) => {
  const found = /^( +)(\S+(?: \S+)*)( {2,})(\S.*)$/.exec(line);
  if (found === null) return undefined;
  const [, lead = "", label = "", gap = "", value = ""] = found;
  // `v7 · Bernardo · 2026-11-16 · "steadier"`: a label of several parts is named by its first.
  const [name = "", ...more] = label.split(DOT);
  return `${lead}${[cyan(name), ...more.map(cell)].join(dim(DOT))}${gap}${cells(value)}`;
};

// `brightside-app  release 2  —`: a table's row, named by its first cell.
const row: Rule = (line) => {
  const found = /^(\S+(?: \S+)*)( {2,}\S.*)$/.exec(line);
  return found === null ? undefined : `${cyan(found[1] ?? "")}${cells(found[2] ?? "")}`;
};

const RULES: readonly Rule[] = [ofAnAgent, refusal, nextStep, mark, turn, section, help, header, title, field, row];

/** A row's cells, each painted when it is a standing's word alone; the gaps between them kept. */
function cells(line: string): string {
  return line
    .split(/( {2,})/)
    .map((part, index) => (index % 2 === 1 ? part : cell(part)))
    .join("");
}

function cell(text: string): string {
  const whole = WORDS[text.trim()];
  if (whole !== undefined) return whole(text);
  // When it happened is read after what happened.
  if (/^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?$/.test(text)) return dim(text);
  // `release 2 failed: the process exited…`: the word that says it went wrong, wherever the cell says it.
  return dots(text).replace(/(?<![\w.])failed\b/, (word) => red(word));
}

function dots(text: string): string {
  return text.split(DOT).join(dim(DOT));
}
