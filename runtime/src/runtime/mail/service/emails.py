"""An email and the frame it is set in: worded once as text and HTML, in the box's brand."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html import escape

from runtime.platform import service as platform

# Inline styles only: mail clients read little CSS. No webfont and no image but the brand's logo.
WASH, INK, MUTED, HAIRLINE = "#f7f6fa", "#101014", "#6b6975", "#eeedf2"
FONT = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
WIDTH = 560
LOGO_HEIGHT = 28


@dataclass(frozen=True, slots=True)
class Email:
    """An email ready to go: to whom, its subject, and the same words as text and as HTML."""

    to: str
    subject: str
    text: str
    html: str


@dataclass(frozen=True, slots=True)
class LinkDetails:
    """What an email with a link says: the org, who sent it, the link, and when it dies."""

    org: str
    link: str
    by: str | None = None
    dies: datetime | None = None


# How an email with a link is worded: an invitation, a reset, a forgotten password.
type Worded = Callable[[str, LinkDetails, platform.Brand], Email]


@dataclass(frozen=True, slots=True)
class Wording:
    """How an email with a link is worded: its subject, its title, what it says, and the button's label."""

    subject: str
    title: str
    said: tuple[str, ...]
    label: str
    unbidden: bool = False


def write_link_email(to: str, link: LinkDetails, brand: platform.Brand, wording: Wording) -> Email:
    """An email whose point is one link: its words, the button, the link again in plain, and when it dies."""
    quiet = ["This link opens once."]
    if wording.unbidden:
        quiet.append("If you did not ask for this, nothing has changed and you can ignore this message.")
    body = (
        heading(wording.title)
        + "".join(paragraph(item) for item in wording.said)
        + button(wording.label, link.link, brand.accent)
        + fallback(link.link)
        + "".join(small(item) for item in quiet)
    )
    sent = f"Sent by {link.org} through {brand.name}"
    footer = sent if link.dies is None else f"{sent} · this link opens once and dies on {day_of(link.dies)}"
    text = "\n\n".join([wording.title, *wording.said, f"Open it in a browser:\n\n{link.link}", *quiet, footer])
    return Email(to, wording.subject, text, frame(wording.said[0], body, footer, brand))


def write_notice(to: str, brand: platform.Brand, title: str, text: str) -> Email:
    """An email that only tells: a title, what happened, and that nothing changed if it was not them."""
    unbidden = "If it was not you, ignore this email: nothing was changed."
    footer = f"Sent by {brand.name}"
    body = heading(title) + paragraph(text) + small(unbidden)
    return Email(
        to,
        f"{title} on {brand.name}",
        f"{title}\n\n{text}\n\n{unbidden}\n\n{footer}",
        frame(text, body, footer, brand),
    )


def day_of(moment: datetime) -> str:
    """The day a moment falls on, as an email says it."""
    return f"{moment.day} {moment.strftime('%B')} {moment.year}"


def heading(text: str) -> str:
    """The email's title."""
    return (
        f'<h1 style="margin:0 0 14px;font-family:{FONT};font-size:21px;line-height:1.3;'
        f'font-weight:650;letter-spacing:-0.02em;color:{INK};">{escape(text)}</h1>'
    )


def paragraph(text: str) -> str:
    """A paragraph of the email's body."""
    return (
        f'<p style="margin:0 0 16px;font-family:{FONT};font-size:15px;line-height:1.6;color:{INK};">{escape(text)}</p>'
    )


def small(text: str) -> str:
    """A quiet line under the body."""
    return (
        f'<p style="margin:0 0 8px;font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};">{escape(text)}</p>'
    )


# A table: Outlook draws an inline-block link wrong.
def button(label: str, href: str, accent: str) -> str:
    """The one button of an email, in the brand's accent."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;">'
        f'<tr><td><a href="{escape(href, quote=True)}" style="display:inline-block;'
        f"background:{accent};color:#ffffff;font-family:{FONT};font-size:15px;font-weight:600;"
        f'text-decoration:none;padding:12px 22px;line-height:18px;border-radius:9px;">'
        f"{escape(label)}</a></td></tr></table>"
    )


def fallback(href: str) -> str:
    """The link again as text, for a client that draws no button."""
    return (
        f'<p style="margin:0 0 16px;font-family:{FONT};font-size:13px;line-height:1.5;'
        f'color:{MUTED};word-break:break-all;">{escape(href)}</p>'
    )


def code_block(code: str) -> str:
    """A code to type, set large and apart."""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;">'
        f'<tr><td align="center" style="background:{WASH};border:1px solid '
        f'{HAIRLINE};border-radius:12px;padding:22px 16px;">'
        f'<div style="font-family:{MONO};font-size:34px;line-height:1;font-weight:600;letter-spacing:10px;'
        f'padding-left:10px;color:{INK};">{escape(code)}</div></td></tr></table>'
    )


def frame(preheader: str, body: str, footer: str, brand: platform.Brand) -> str:
    """The whole HTML of an email: the brand's logo or name, the body, the footer."""
    logo = (
        ""
        if brand.logo_url is None
        else (
            '<tr><td style="padding:0 6px 16px;">'
            f'<img src="{escape(brand.logo_url, quote=True)}" alt="{escape(brand.name, quote=True)}" '
            f'height="{LOGO_HEIGHT}" style="display:block;height:{LOGO_HEIGHT}px;width:auto;border:0;"></td></tr>'
        )
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light only"></head>'
        f'<body style="margin:0;padding:0;background:{WASH};">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{WASH};padding:36px 14px;"><tr><td align="center">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:{WIDTH}px;">{logo}'
        f'<tr><td style="background:#ffffff;border:1px solid {HAIRLINE};border-radius:14px;padding:30px 30px '
        f'24px;">{body}</td></tr>'
        f'<tr><td style="padding:18px 6px '
        f'0;font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED};">{escape(footer)}</td></tr>'
        "</table></td></tr></table></body></html>"
    )


def test_email(to: str, brand: platform.Brand) -> Email:
    """The test email that proves a mailbox sends."""
    text = (
        f"This is a test message from {brand.name}. Your mail server took it, so the emails "
        "this gateway sends will reach you."
    )
    body = heading("It works") + paragraph(text)
    return Email(to, f"{brand.name} test message", text, frame(text, body, brand.name, brand))
