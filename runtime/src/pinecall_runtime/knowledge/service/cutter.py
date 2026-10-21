"""The Markdown cutter: a file into pieces under a token cap, each with its heading path and its questions."""

import hashlib
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from pinecall_runtime.knowledge.service.embedder import estimated_tokens

# Small enough for eight chunks a turn, large enough for a whole tariff table.
CHUNK_TOKENS = 350
# U+203A, the single right-pointing angle quote the stored heading paths are joined with.
HEADING_SEPARATOR = " › "
# Both indexes read the heading path above the body, so a heading's words are searchable.
HEADING_JOINT = "\n\n"
# Only levels 1 to 3 cut a file; a deeper heading is body.
A_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
# A line inside a code fence is never a heading: `# install` in a shell block is a comment.
A_FENCE = re.compile(r"^\s*(```|~~~)")
A_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
A_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Front matter is metadata: left in, a scraped site's became a chunk per page.
FRONT_MATTER = "---\n"
A_CLOSING_RULE = re.compile(r"^---[ \t]*$", re.MULTILINE)
# An HTML comment is for the author, never for the model or an index; the `asks` ones carry the
# questions the section answers, one a line, invisible on any site that renders the file.
A_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
ASKS = "asks"


@dataclass(frozen=True, slots=True)
class Piece:
    """One chunk of a file before it is embedded: its heading path, its body, and the questions it answers."""

    path: str
    heading: str | None
    ordinal: int
    text: str
    asks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Cut:
    """A file as a push writes it: its text, the hash of it, and its pieces."""

    path: str
    text: str
    sha256: str
    pieces: tuple[Piece, ...]

    @property
    def rows(self) -> int:
        """How many rows the file becomes: its pieces and the questions they answer."""
        return sum(1 + len(piece.asks) for piece in self.pieces)


def cut(path: str, text: str) -> Cut:
    """The file cut once, with the hash a later push compares against."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Cut(path, text, digest, tuple(chunks_of(path, text)))


def chunks_of(path: str, text: str) -> list[Piece]:
    """The file cut at its headings, each piece under the cap, in file order; a section's questions ride its first."""
    pieces: list[Piece] = []
    for heading, commented in _sections_of(_without_front_matter(text)):
        body, asks = _without_comments(commented)
        for at, group in enumerate(_under_the_cap(body, heading)):
            pieces.append(Piece(path, heading, len(pieces), group, asks if at == 0 else ()))
    return pieces


def indexed_text(piece: Piece) -> str:
    """What both indexes read: the heading path above the body, or the body alone."""
    return f"{piece.heading}{HEADING_JOINT}{piece.text}" if piece.heading else piece.text


def body_of(indexed: str, heading: str | None) -> str:
    """The indexed text without its heading path: what the model reads."""
    return indexed.removeprefix(f"{heading}{HEADING_JOINT}") if heading else indexed


def where(path: str, heading: str | None) -> str:
    """The chunk's file, then its heading path."""
    return f"{path}{HEADING_SEPARATOR}{heading}" if heading else path


# A file answers for every chunk of it and a heading for its section and what is under it; by
# prefix and separator, never substring: `tarifas.md` is not `tarifas-2024.md`.
def answers(found: str, expects: str) -> bool:
    """Whether a chunk's heading path is the one a golden expects, or under it."""
    wanted = expects.strip()
    return found == wanted or found.startswith(f"{wanted}{HEADING_SEPARATOR}")


# An unclosed `---` is a horizontal rule, and the file is left as it is.
def _without_front_matter(text: str) -> str:
    if not text.startswith(FRONT_MATTER):
        return text
    closed = A_CLOSING_RULE.search(text, len(FRONT_MATTER))
    return text[closed.end() :].lstrip("\n") if closed else text


# Outside a code fence a comment is dropped whole; an `asks` comment gives its lines first. Inside
# a fence a comment is code and stays.
def _without_comments(body: str) -> tuple[str, tuple[str, ...]]:
    kept: list[str] = []
    asks: list[str] = []
    for fenced, run in _runs_of(body):
        if fenced:
            kept.append(run)
            continue
        for comment in A_COMMENT.finditer(run):
            lines = [line.strip() for line in comment.group(1).strip().splitlines()]
            if lines and lines[0] == ASKS:
                asks.extend(line for line in lines[1:] if line)
        kept.append(A_COMMENT.sub("", run))
    return "".join(kept), tuple(dict.fromkeys(asks))


# The body as runs of lines, each fenced or not, with their line breaks.
def _runs_of(body: str) -> Iterator[tuple[bool, str]]:
    fence: str | None = None
    run: list[str] = []
    fenced = False
    for line in body.split("\n"):
        opened = A_FENCE.match(line)
        if opened is not None and fence in {None, opened.group(1)}:
            if fence is None:
                if run:
                    yield fenced, "\n".join(run) + "\n"
                run, fenced, fence = [line], True, opened.group(1)
                continue
            run.append(line)
            yield True, "\n".join(run) + "\n"
            run, fenced, fence = [], False, None
            continue
        run.append(line)
    if run:
        yield fenced, "\n".join(run)


# A level-n heading closes the open headings of level n and deeper.
def _sections_of(text: str) -> Iterator[tuple[str | None, str]]:
    trail: list[tuple[int, str]] = []
    body: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        fenced = A_FENCE.match(line)
        if fenced is not None and fence in {None, fenced.group(1)}:
            fence = None if fence else fenced.group(1)
        heading = None if fence or fenced else A_HEADING.match(line)
        if heading is None:
            body.append(line)
            continue
        yield _path_of(trail), "\n".join(body)
        body = []
        level = len(heading.group(1))
        trail = [*(kept for kept in trail if kept[0] < level), (level, heading.group(2))]
    yield _path_of(trail), "\n".join(body)


def _path_of(trail: Sequence[tuple[int, str]]) -> str | None:
    return HEADING_SEPARATOR.join(title for _, title in trail) or None


# The heading's tokens count against the cap: it is indexed with every piece under it.
def _under_the_cap(body: str, heading: str | None) -> list[str]:
    room = CHUNK_TOKENS - estimated_tokens(heading or "")
    parts = [part for paragraph in _paragraphs(body) for part in _within(paragraph, room)]
    return _grouped(parts, HEADING_JOINT, room)


# A blank line inside a code fence is the code's own: the block stays one paragraph, so a class
# is never cut between two of its members and handed back as two halves.
def _paragraphs(body: str) -> list[str]:
    paragraphs: list[str] = []
    in_code = False
    for paragraph in A_PARAGRAPH_BREAK.split(body):
        if in_code:
            paragraphs[-1] += HEADING_JOINT + paragraph
        else:
            paragraphs.append(paragraph)
        if sum(1 for line in paragraph.splitlines() if A_FENCE.match(line)) % 2:
            in_code = not in_code
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def _within(paragraph: str, room: int) -> list[str]:
    if estimated_tokens(paragraph) <= room or A_FENCE.match(paragraph):
        return [paragraph]
    return _grouped(A_SENTENCE_END.split(paragraph), " ", room)


# A part longer than the room is kept whole rather than cut mid-sentence.
def _grouped(parts: Sequence[str], joint: str, room: int) -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    for part in parts:
        if current and estimated_tokens(joint.join([*current, part])) > room:
            groups.append(joint.join(current))
            current = []
        current.append(part)
    if current:
        groups.append(joint.join(current))
    return groups
