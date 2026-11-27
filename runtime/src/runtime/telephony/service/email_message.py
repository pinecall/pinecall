"""An email as the agent reads it (its words alone, the quoted past cut off), and as an app's flow reads it, whole."""

import logging
import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import override

from runtime.enums import Channel
from runtime.whatsapp import service as whatsapp

logger = logging.getLogger(__name__)

# An email that cannot be read whole is cut here: a reply is a few paragraphs, never a document.
LONGEST = 8000
_MESSAGE_ID = re.compile(r"<[^<>\s]+>")
# Where a reply's quoted past begins, in the clients people write from: Gmail's and Apple Mail's
# "On … wrote:" in English or Spanish, Outlook's header block and its line.
_QUOTED = re.compile(
    r"^\s*(On .{6,}wrote:|El .{6,}escribi[oó]:|-{2,}\s*Original Message\s*-{2,}|_{10,}|From:\s.+|De:\s.+)\s*$",
    re.IGNORECASE,
)
# Who never writes as a person: a bounce, a robot, an address nobody reads.
_ROBOTS = re.compile(r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply|bounces?)([+@.-]|$)", re.IGNORECASE)


def read_email(raw: bytes, address: str, fallback_id: str) -> whatsapp.Inbound | None:
    """The email as a message of a thread; None for one nobody should answer (a robot, a list, the mailbox itself)."""
    message = message_from_bytes(raw, policy=policy.default)
    name, sender = parseaddr(str(message.get("From", "")))
    sender = sender.strip().lower()
    why = _why_unanswered(message, sender, address)
    if why is not None:
        logger.info("email: a message to %s is not answered: %s", address, why)
        return None
    message_id = _ids_in(str(message.get("Message-ID", "")))[:1] or [fallback_id]
    references = _ids_in(str(message.get("References", ""))) or _ids_in(str(message.get("In-Reply-To", "")))
    text = cut_quoted(_text_of(message))
    if not text:
        logger.info("email: a message to %s from %s says nothing once its quoted past is cut", address, sender)
        return None
    return whatsapp.Inbound(
        number=address,
        phone_number_id=address,
        wa_id=sender,
        name=name.strip() or None,
        message_id=message_id[0],
        kind="text",
        text=text[:LONGEST],
        channel=Channel.email,
        subject=str(message.get("Subject", "")).strip() or None,
        references=tuple(references),
        thread=(references or message_id)[0],
    )


# A reply that is written by no person (RFC 3834), a bulk or list email, or one of the mailbox's own
# (a copy, a loop) is read and never answered: two robots answering each other never stop.
@dataclass(frozen=True, slots=True)
class Mail:
    """An email as the event `mail.received` carries it to an app: who wrote, to whom, the subject, the words."""

    to: str
    sender: str
    sender_name: str | None
    subject: str | None
    text: str
    message_id: str
    # ISO 8601, as its Date header says it; None when it says none that reads.
    date: str | None


# An address an app's flows read (`routes.app`) takes every email, a machine's above all: a portal's lead
# or an order is written by no person, so nothing is filtered but the mailbox's own (a loop) and one that
# says nothing. The words are read whole, quotes and all: a forwarded notice is what is below the header.
def read_mail(raw: bytes, address: str, fallback_id: str, longest: int) -> Mail | None:
    """The email whole for an app's flow, cut at `longest` characters; None for the mailbox's own or an empty one."""
    message = message_from_bytes(raw, policy=policy.default)
    name, sender = parseaddr(str(message.get("From", "")))
    sender = sender.strip().lower()
    text = _text_of(message).strip()
    if sender == address or not text:
        logger.info("email: a message to %s is not handed to its app: %s", address, "its own" if text else "empty")
        return None
    return Mail(
        to=address,
        sender=sender,
        sender_name=name.strip() or None,
        subject=str(message.get("Subject", "")).strip() or None,
        text=text[:longest],
        message_id=(_ids_in(str(message.get("Message-ID", ""))) or [fallback_id])[0],
        date=_date_of(str(message.get("Date", ""))),
    )


def _date_of(header: str) -> str | None:
    try:
        return parsedate_to_datetime(header).isoformat() if header.strip() else None
    except (TypeError, ValueError):
        return None


def _why_unanswered(message: EmailMessage, sender: str, address: str) -> str | None:
    if not sender:
        return "it names no sender"
    if sender == address:
        return "the mailbox wrote it itself"
    if _ROBOTS.match(sender):
        return f"{sender} is no person"
    if str(message.get("Auto-Submitted", "no")).strip().lower() != "no":
        return "it was written by a machine (Auto-Submitted)"
    if str(message.get("Precedence", "")).strip().lower() in ("bulk", "list", "junk", "auto_reply"):
        return "it was sent in bulk"
    if message.get("List-Id") is not None or message.get("List-Unsubscribe") is not None:
        return "it came from a mailing list"
    written_to = [*message.get_all("To", []), *message.get_all("Cc", [])]
    recipients = {found.lower() for _, found in getaddresses(written_to)}
    if recipients and address not in recipients and message.get("Delivered-To") is None:
        return "the mailbox was a blind copy"
    return None


def cut_quoted(text: str) -> str:
    """The writer's own words: from the line a client quotes the past under, all is cut, and so is a signature."""
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if _QUOTED.match(line) or line.rstrip() == "--":
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _ids_in(header: str) -> list[str]:
    return _MESSAGE_ID.findall(header)


# The plain part when the email has one, as every client sends; else its HTML, as text.
def _text_of(message: EmailMessage) -> str:
    plain = message.get_body(preferencelist=("plain",))
    if plain is not None:
        return str(plain.get_content())
    rich = message.get_body(preferencelist=("html",))
    return "" if rich is None else text_of_html(str(rich.get_content()))


def text_of_html(html: str) -> str:
    """The words of an HTML email, a line a block, its styles and scripts left out."""
    reader = _Words()
    reader.feed(html)
    reader.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(reader.words)).strip()


_BLOCKS = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "table"})


class _Words(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.words: list[str] = []
        self._skipping = 0

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script", "head"):
            self._skipping += 1
        elif tag in _BLOCKS:
            self.words.append("\n")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "head"):
            self._skipping = max(0, self._skipping - 1)
        elif tag in _BLOCKS:
            self.words.append("\n")

    @override
    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.words.append(data)
