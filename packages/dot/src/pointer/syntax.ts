/** TypeScript and TSX coloured as an editor colours them: each line its pieces, each piece what it is. Pure. */
//
// A small tokenizer, not a parser: enough for the code a walk explains (a class, its fields, a tool,
// its view). A block comment runs across lines, so the state is carried from one line to the next.

/** What a piece of a line is. */
export type Kind = "plain" | "comment" | "keyword" | "string" | "decorator" | "type" | "tag" | "number" | "self";

export interface Piece {
  text: string;
  kind: Kind;
}

const KEYWORDS = new Set([
  "export", "import", "from", "default", "class", "extends", "implements", "interface", "type", "enum", "const", "let", "var",
  "function", "return", "if", "else", "for", "of", "in", "while", "async", "await", "new", "static", "override", "private",
  "public", "readonly", "true", "false", "null", "undefined", "void", "as", "throw", "try", "catch", "finally",
]);

// One alternative per kind, tried in order at each position.
const PIECES = /(\/\/.*$)|(\/\*.*?(?:\*\/|$))|("(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?|`(?:[^`\\]|\\.)*`?)|(@[A-Za-z_]\w*)|(<\/?[a-z][\w.-]*|\/?>)|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_$][\w$]*\b)/g;

/** Each line of `text` as its pieces, in order; joined, a line's pieces are the line. */
export function coloured(text: string): Piece[][] {
  let inComment = false;
  return text.split("\n").map((line) => {
    const pieces: Piece[] = [];
    let at = 0;
    if (inComment) {
      const end = line.indexOf("*/");
      const upto = end === -1 ? line.length : end + 2;
      pieces.push({ text: line.slice(0, upto), kind: "comment" });
      at = upto;
      inComment = end === -1;
    }
    PIECES.lastIndex = at;
    for (let found = PIECES.exec(line); found !== null; found = PIECES.exec(line)) {
      if (found.index > at) pieces.push({ text: line.slice(at, found.index), kind: "plain" });
      const [whole, lineComment, blockComment, string, decorator, tag, number] = found;
      let kind: Kind = "plain";
      if (lineComment !== undefined) kind = "comment";
      else if (blockComment !== undefined) {
        kind = "comment";
        inComment = !blockComment.endsWith("*/") || blockComment.length < 4;
      } else if (string !== undefined) kind = "string";
      else if (decorator !== undefined) kind = "decorator";
      else if (tag !== undefined) kind = "tag";
      else if (number !== undefined) kind = "number";
      else if (whole === "this" || whole === "super") kind = "self";
      else if (KEYWORDS.has(whole)) kind = "keyword";
      else if (/^[A-Z]/.test(whole)) kind = "type";
      pieces.push({ text: whole, kind });
      at = found.index + whole.length;
      if (whole.length === 0) PIECES.lastIndex += 1;
    }
    if (at < line.length) pieces.push({ text: line.slice(at), kind: "plain" });
    return pieces;
  });
}
