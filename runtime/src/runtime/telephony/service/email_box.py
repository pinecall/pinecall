"""A mailbox's inbox over IMAP: the messages written to it since the last one read, and the check that it opens."""

import asyncio
import contextlib
import imaplib
import re
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from runtime.exceptions import UpstreamError
from runtime.kit import dns

TIMEOUT_S = 15.0
# A pass reads this many messages at most: what is left is read on the next, in order.
MOST_A_PASS = 20
# What STATUS answers about the inbox.
_STATUS = re.compile(rb"UIDNEXT (\d+)|UIDVALIDITY (\d+)")


@dataclass(frozen=True, slots=True)
class ImapServer:
    """Where an inbox is read, and the login that opens it: always over TLS."""

    host: str
    port: int
    login: str
    password: str


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where the reading of an inbox stood: its UIDVALIDITY and the newest UID read; none before the first pass."""

    uid_validity: int | None = None
    last_uid: int | None = None


@dataclass(frozen=True, slots=True)
class Page:
    """What a pass read: each new message with its UID, oldest first, and where the reading stands after it."""

    messages: tuple[tuple[int, bytes], ...]
    cursor: Cursor


async def check_inbox(server: ImapServer) -> None:
    """Log in and open the inbox, reading nothing; UpstreamError in the server's words when it refuses."""
    await _in_a_thread(_open_and_close, server)


# The first pass reads nothing and only says where the inbox stands: a mailbox routed to an agent is not
# made to answer its whole past. A mailbox whose UIDVALIDITY changed numbered its messages anew, and is
# taken from where it stands the same way.
async def read_new(server: ImapServer, cursor: Cursor) -> Page:
    """The messages that came after the cursor, oldest first, each marked read; where the reading stands after."""
    return await _in_a_thread(_read_new, server, cursor)


async def _in_a_thread[**P, T](work: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return await asyncio.wait_for(asyncio.to_thread(work, *args, **kwargs), TIMEOUT_S * 2)
    except TimeoutError:
        raise UpstreamError(f"the inbox did not answer in {TIMEOUT_S * 2:g}s") from None


def _open_and_close(server: ImapServer) -> None:
    with _Session(server) as inbox:
        _select(inbox, server)


def _read_new(server: ImapServer, cursor: Cursor) -> Page:
    with _Session(server) as inbox:
        _select(inbox, server)
        validity, next_uid = _status(inbox, server)
        if cursor.last_uid is None or cursor.uid_validity != validity:
            return Page((), Cursor(validity, next_uid - 1))
        newer = [uid for uid in _search_after(inbox, server, cursor.last_uid) if uid > cursor.last_uid]
        read: list[tuple[int, bytes]] = []
        for uid in sorted(newer)[:MOST_A_PASS]:
            read.append((uid, _fetch(inbox, server, uid)))
        last = read[-1][0] if read else cursor.last_uid
        return Page(tuple(read), Cursor(validity, last))


# The host is checked to resolve to the internet alone, as an org's SMTP server is: a mailbox an org
# names cannot reach into the box's own network. It is then connected to by name (owed: D6).
class _Session:
    def __init__(self, server: ImapServer) -> None:
        self.server = server
        self.inbox: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> imaplib.IMAP4_SSL:
        server = self.server
        try:
            addresses = dns.resolve(server.host)
        except OSError:
            raise UpstreamError(f"{server.host} resolves to no address") from None
        if not dns.all_public(addresses):
            raise UpstreamError(f"{server.host} resolves to no public address, or to one that is not")
        try:
            self.inbox = imaplib.IMAP4_SSL(
                server.host, server.port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT_S
            )
            self.inbox.login(server.login, server.password)
        except imaplib.IMAP4.error as refused:
            raise UpstreamError(f"{server.host}:{server.port} refused the login: {_refusal_of(refused)}") from refused
        except OSError as down:
            raise UpstreamError(f"{server.host}:{server.port} did not answer: {type(down).__name__}: {down}") from down
        return self.inbox

    def __exit__(self, *_: object) -> None:
        if self.inbox is not None:
            with contextlib.suppress(imaplib.IMAP4.error, OSError):
                self.inbox.logout()


def _select(inbox: imaplib.IMAP4_SSL, server: ImapServer) -> None:
    typed, said = inbox.select("INBOX")
    if typed != "OK":
        raise UpstreamError(f"{server.host} would not open the inbox: {_words(said)}")


def _status(inbox: imaplib.IMAP4_SSL, server: ImapServer) -> tuple[int, int]:
    typed, said = inbox.status("INBOX", "(UIDNEXT UIDVALIDITY)")
    found = {"next": 0, "validity": 0}
    for item in said if typed == "OK" else []:
        for match in _STATUS.finditer(item if isinstance(item, bytes) else b""):
            if match.group(1):
                found["next"] = int(match.group(1))
            if match.group(2):
                found["validity"] = int(match.group(2))
    if not found["next"] or not found["validity"]:
        raise UpstreamError(f"{server.host} did not say where its inbox stands: {_words(said)}")
    return found["validity"], found["next"]


def _search_after(inbox: imaplib.IMAP4_SSL, server: ImapServer, last: int) -> list[int]:
    typed, said = inbox.uid("SEARCH", f"UID {last + 1}:*")
    if typed != "OK":
        raise UpstreamError(f"{server.host} would not search its inbox: {_words(said)}")
    found = said[0] if said and isinstance(said[0], bytes) else b""
    return [int(uid) for uid in found.split()]


# Fetched whole and marked read, as a person opening it would leave it.
def _fetch(inbox: imaplib.IMAP4_SSL, server: ImapServer, uid: int) -> bytes:
    typed, said = inbox.uid("FETCH", str(uid), "(BODY.PEEK[])")
    whole = _body_of(said)
    if typed != "OK" or whole is None:
        raise UpstreamError(f"{server.host} would not hand over message {uid}: {_words(said)}")
    inbox.uid("STORE", str(uid), "+FLAGS", "(\\Seen)")
    return whole


def _refusal_of(refused: Exception) -> str:
    first = refused.args[0] if refused.args else refused
    return first.decode("utf-8", "replace") if isinstance(first, bytes) else str(first)


# imaplib answers a fetch as a list whose parts are a pair (what was asked, the bytes) or a closing byte string.
def _body_of(said: Sequence[object]) -> bytes | None:
    for part in said:
        if isinstance(part, tuple):
            pair = cast("tuple[object, ...]", part)
            if len(pair) > 1 and isinstance(pair[1], bytes):
                return pair[1]
    return None


def _words(said: Sequence[object]) -> str:
    first = said[0] if said else b""
    return first.decode("utf-8", "replace") if isinstance(first, bytes) else str(first)
