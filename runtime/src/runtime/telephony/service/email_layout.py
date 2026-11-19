"""How an agent's email is set: in the org's own HTML layout, in a plain one, or as text alone."""

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

_IMAGE = re.compile(r"!\[([^\]\n]*)\]\((https?://[^\s)]+)\)")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_URL = re.compile(r"(?<![\"'>=])\b(https?://[^\s<]+[^\s<.,;:!?)\]'\"])")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")


@dataclass(frozen=True, slots=True)
class Layout:
    """The org's layout, or the plain one, whether it is the org's own, and whether its emails go as text alone."""

    html: str
    own: bool
    # No HTML part at all: the email is its words, one `text/plain` part. The org's choice, never the default.
    text_only: bool = False


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
    if row is None:
        return Layout(PLAIN, own=False)
    return Layout(PLAIN, own=True, text_only=True) if row.text_only else Layout(row.html, own=True)


async def put_layout(session: AsyncSession, org: str, html: str, *, by: str | None) -> Layout:
    """Keep the org's layout, its agents' next emails set in it."""
    await EmailLayoutRepository(session).put(org, check_layout(html), text_only=False, by=by, at=now())
    return Layout(html, own=True)


# An org that wants no template at all: its emails are their words, and a client shows them in its own font.
async def send_text_only(session: AsyncSession, org: str, *, by: str | None) -> Layout:
    """Keep that the org's agents' emails go as text alone, with no HTML part."""
    await EmailLayoutRepository(session).put(org, "", text_only=True, by=by, at=now())
    return Layout(PLAIN, own=True, text_only=True)


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


# An image is the one thing a reply shows that is not its words: `![what it is](https://…)`, as wide as the email.
_IMG = r'<img src="\2" alt="\1" style="max-width:100%;height:auto;border:0;">'


def _inline(line: str) -> str:
    written = escape(line.strip())
    written = _IMAGE.sub(_IMG, written)
    written = _LINK.sub(r'<a href="\2">\1</a>', written)
    written = _URL.sub(r'<a href="\1">\1</a>', written)
    written = _BOLD.sub(r"<strong>\1</strong>", written)
    return _ITALIC.sub(r"<em>\1</em>", written)


def text_of(text: str) -> str:
    """The reply as the plain part says it: the marks taken off, a link's or an image's address beside its words."""
    plain = _LINK.sub(r"\1 (\2)", _IMAGE.sub(r"\1 (\2)", text.strip()))
    return _ITALIC.sub(r"\1", _BOLD.sub(r"\1", plain))
