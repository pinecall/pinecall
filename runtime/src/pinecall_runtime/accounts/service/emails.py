"""The emails the gateway sends, worded once as text and HTML, framed in the box's brand."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html import escape

from pinecall_runtime.platform import service as platform

CARD = "/invitations/{token}"

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
class _Wording:
    subject: str
    title: str
    said: tuple[str, ...]
    label: str
    unbidden: bool = False


def card_link(base: str, token: str) -> str:
    """The console's card for a token, at the name this gateway answers to."""
    return f"{base.rstrip('/')}{CARD.format(token=token)}"


def invitation_email(to: str, link: LinkDetails, brand: platform.Brand) -> Email:
    """The email that invites a person into an org."""
    return _linked(
        to,
        link,
        brand,
        _Wording(
            subject=f"You're invited to {link.org} on {brand.name}",
            title="Join your team",
            said=(
                f"{link.by} has invited you to join {link.org} on {brand.name}.",
                "Choose a password and you are in.",
            ),
            label="Accept the invitation",
        ),
    )


def reset_email(to: str, link: LinkDetails, brand: platform.Brand) -> Email:
    """The email an admin's reset of a member's password sends."""
    return _linked(
        to,
        link,
        brand,
        _Wording(
            subject=f"Reset your {brand.name} password",
            title="Set a new password",
            said=(f"{link.by} has reset your password for {link.org}.", "Choose a new one to sign in again."),
            label="Choose a password",
        ),
    )


def forgotten_password_email(to: str, link: LinkDetails, brand: platform.Brand) -> Email:
    """The email a forgotten password sends, which nobody may have asked for."""
    return _linked(
        to,
        link,
        brand,
        _Wording(
            subject=f"Reset your {brand.name} password",
            title="Reset your password",
            said=(f"Somebody asked to reset the password for this address at {link.org}.",),
            label="Choose a password",
            unbidden=True,
        ),
    )


def test_email(to: str, brand: platform.Brand) -> Email:
    """The test email that proves a mailbox sends."""
    text = (
        f"This is a test message from {brand.name}. Your mail server took it, so the emails "
        "this gateway sends will reach you."
    )
    body = _heading("It works") + _paragraph(text)
    return Email(to, f"{brand.name} test message", text, _framed(text, body, brand.name, brand))


def account_exists_email(to: str, brand: platform.Brand) -> Email:
    """Sent instead of a sign-up code when the address has an account already."""
    return _notice(
        to,
        brand,
        "You already have an account",
        (
            f"Somebody tried to sign up for {brand.name} with this address, which already has an "
            "account. To make another org, sign up again with the password you have; if you forgot "
            "it, reset it from the sign-in page."
        ),
    )


def invitation_waiting_email(to: str, brand: platform.Brand) -> Email:
    """Sent instead of a sign-up code when the address was invited somewhere."""
    return _notice(
        to,
        brand,
        "You have an invitation waiting",
        (
            f"Somebody tried to sign up for {brand.name} with this address, which was invited to an "
            "org. Accept that invitation first, from the email it came in; then sign up with the "
            "password you chose there."
        ),
    )


# The code rides the preheader, never the subject: the outbox logs subjects.
def signup_code_email(to: str, code: str, person: str, brand: platform.Brand) -> Email:
    """The email that carries a sign-up's six digits."""
    intro = f"Hi {person}, enter this code to finish setting up your {brand.name} account:"
    dies = "This code expires in 15 minutes."
    unbidden = f"If you did not create a {brand.name} account, ignore this email."
    footer = f"Sent by {brand.name}"
    body = _heading("Confirm your email") + _paragraph(intro) + _code(code) + _small(dies) + _small(unbidden)
    text = f"Confirm your email\n\n{intro}\n\n{code}\n\n{dies}\n\n{unbidden}\n\n{footer}"
    return Email(
        to,
        f"Confirm your {brand.name} email",
        text,
        _framed(f"Your {brand.name} verification code is {code}", body, footer, brand),
    )


def _linked(to: str, link: LinkDetails, brand: platform.Brand, wording: _Wording) -> Email:
    quiet = ["This link opens once."]
    if wording.unbidden:
        quiet.append("If you did not ask for this, nothing has changed and you can ignore this message.")
    body = (
        _heading(wording.title)
        + "".join(_paragraph(item) for item in wording.said)
        + _button(wording.label, link.link, brand.accent)
        + _fallback(link.link)
        + "".join(_small(item) for item in quiet)
    )
    sent = f"Sent by {link.org} through {brand.name}"
    footer = sent if link.dies is None else f"{sent} · this link opens once and dies on {_day(link.dies)}"
    text = "\n\n".join([wording.title, *wording.said, f"Open it in a browser:\n\n{link.link}", *quiet, footer])
    return Email(to, wording.subject, text, _framed(wording.said[0], body, footer, brand))


def _notice(to: str, brand: platform.Brand, title: str, text: str) -> Email:
    unbidden = "If it was not you, ignore this email: nothing was changed."
    footer = f"Sent by {brand.name}"
    body = _heading(title) + _paragraph(text) + _small(unbidden)
    return Email(
        to,
        f"{title} on {brand.name}",
        f"{title}\n\n{text}\n\n{unbidden}\n\n{footer}",
        _framed(text, body, footer, brand),
    )


def _day(moment: datetime) -> str:
    return f"{moment.day} {moment.strftime('%B')} {moment.year}"


def _heading(text: str) -> str:
    return (
        f'<h1 style="margin:0 0 14px;font-family:{FONT};font-size:21px;line-height:1.3;'
        f'font-weight:650;letter-spacing:-0.02em;color:{INK};">{escape(text)}</h1>'
    )


def _paragraph(text: str) -> str:
    return (
        f'<p style="margin:0 0 16px;font-family:{FONT};font-size:15px;line-height:1.6;color:{INK};">{escape(text)}</p>'
    )


def _small(text: str) -> str:
    return (
        f'<p style="margin:0 0 8px;font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};">{escape(text)}</p>'
    )


# A table: Outlook draws an inline-block link wrong.
def _button(label: str, href: str, accent: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;">'
        f'<tr><td><a href="{escape(href, quote=True)}" style="display:inline-block;'
        f"background:{accent};color:#ffffff;font-family:{FONT};font-size:15px;font-weight:600;"
        f'text-decoration:none;padding:12px 22px;line-height:18px;border-radius:9px;">'
        f"{escape(label)}</a></td></tr></table>"
    )


def _fallback(href: str) -> str:
    return (
        f'<p style="margin:0 0 16px;font-family:{FONT};font-size:13px;line-height:1.5;'
        f'color:{MUTED};word-break:break-all;">{escape(href)}</p>'
    )


def _code(code: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;">'
        f'<tr><td align="center" style="background:{WASH};border:1px solid '
        f'{HAIRLINE};border-radius:12px;padding:22px 16px;">'
        f'<div style="font-family:{MONO};font-size:34px;line-height:1;font-weight:600;letter-spacing:10px;'
        f'padding-left:10px;color:{INK};">{escape(code)}</div></td></tr></table>'
    )


def _framed(preheader: str, body: str, footer: str, brand: platform.Brand) -> str:
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
