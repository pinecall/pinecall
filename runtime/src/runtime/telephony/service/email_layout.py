"""The HTML an agent's email is set in: the org's own layout, or a plain one, with the reply written in as HTML."""

import re
from dataclasses import dataclass
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import ValidationError
from runtime.kit.time import now
from runtime.telephony.repository import EmailLayoutRepository

# Where the reply goes in a layout, once; the subject may go anywhere, as often as the org likes.
CONTENT = "{{content}}"
SUBJECT = "{{subject}}"
LONGEST = 200_000

# The layout of an org that wrote none: the reply on white, in the reader's own font, nobody's brand.
PLAIN = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:24px;background:#ffffff;">
<div style="max-width:600px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;\
font-size:15px;line-height:1.55;color:#1d1d1f;">{{content}}</div>
</body></html>
"""

_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_URL = re.compile(r"(?<![\"'>=])\b(https?://[^\s<]+[^\s<.,;:!?)\]'\"])")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")


@dataclass(frozen=True, slots=True)
class Layout:
    """The org's layout, or the plain one, and whether it is the org's own."""

    html: str
    own: bool


def check_layout(html: str) -> str:
    """The layout, when it says once where the reply goes and is small enough to send."""
    if len(html) > LONGEST:
        raise ValidationError(f"a layout is {LONGEST:,} characters at most, and this one is {len(html):,}")
    if html.count(CONTENT) != 1:
        raise ValidationError(f"a layout says once where the reply goes, with {CONTENT}")
    return html


async def layout_of(session: AsyncSession, org: str) -> Layout:
    """The org's layout, or the plain one while it wrote none."""
    row = await EmailLayoutRepository(session).find(org)
    return Layout(PLAIN, own=False) if row is None else Layout(row.html, own=True)


async def put_layout(session: AsyncSession, org: str, html: str, *, by: str | None) -> Layout:
    """Keep the org's layout, its agents' next emails set in it."""
    await EmailLayoutRepository(session).put(org, check_layout(html), by=by, at=now())
    return Layout(html, own=True)


async def delete_layout(session: AsyncSession, org: str) -> bool:
    """Forget the org's layout, back to the plain one; whether it had one."""
    return await EmailLayoutRepository(session).delete_of(org)


def set_in(layout: str, text: str, *, subject: str) -> str:
    """The reply written in as HTML where the layout says, and the subject wherever it asks for it."""
    return layout.replace(SUBJECT, escape(subject)).replace(CONTENT, html_of(text))


# What a model writes in an email, read as the few marks a reader expects to see: paragraphs, lists,
# bold and italics, links. Everything else is text, escaped: nothing a contact's words or a model's
# put in the reply can be HTML of its own.
def html_of(text: str) -> str:
    """The reply's words as HTML: a paragraph a block, a list where the lines are bullets, its links live."""
    blocks = [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]
    return "\n".join(_block(block.split("\n")) for block in blocks)


def _block(lines: list[str]) -> str:
    if all(_BULLET.match(line) for line in lines):
        return "<ul>" + "".join(f"<li>{_inline(_BULLET.sub(r'\1', line))}</li>" for line in lines) + "</ul>"
    if all(_NUMBERED.match(line) for line in lines):
        return "<ol>" + "".join(f"<li>{_inline(_NUMBERED.sub(r'\1', line))}</li>" for line in lines) + "</ol>"
    return '<p style="margin:0 0 14px;">' + "<br>".join(_inline(line) for line in lines) + "</p>"


def _inline(line: str) -> str:
    written = escape(line.strip())
    written = _LINK.sub(r'<a href="\2">\1</a>', written)
    written = _URL.sub(r'<a href="\1">\1</a>', written)
    written = _BOLD.sub(r"<strong>\1</strong>", written)
    return _ITALIC.sub(r"<em>\1</em>", written)


def text_of(text: str) -> str:
    """The reply as the plain part says it: the marks taken off, a link's address beside its words."""
    plain = _LINK.sub(r"\1 (\2)", text.strip())
    return _ITALIC.sub(r"\1", _BOLD.sub(r"\1", plain))
