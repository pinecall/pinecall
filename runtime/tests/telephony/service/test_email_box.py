"""An inbox read over IMAP: the first pass reads nothing and says where it stands; later ones read what came after."""

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from runtime.telephony.service import email_box
from runtime.telephony.service.email_box import Cursor, ImapServer

SERVER = ImapServer("mail.acme.example", 993, "help@acme.example", "p")


@dataclass
class Inbox:
    """An IMAP inbox as imaplib answers: its UIDVALIDITY, its messages by UID, and what was marked read."""

    validity: int = 7
    messages: dict[int, bytes] = field(default_factory=dict[int, bytes])
    seen: list[int] = field(default_factory=list[int])

    def select(self, _box: str) -> tuple[str, list[bytes]]:
        return "OK", [str(len(self.messages)).encode()]

    def status(self, _box: str, _asked: str) -> tuple[str, list[bytes]]:
        following = max(self.messages, default=0) + 1
        return "OK", [f"INBOX (UIDNEXT {following} UIDVALIDITY {self.validity})".encode()]

    def uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        if command == "SEARCH":
            first = int(args[0].split()[1].split(":")[0])
            found = [uid for uid in self.messages if uid >= first] or [max(self.messages, default=0)]
            return "OK", [" ".join(str(uid) for uid in found).encode()]
        if command == "FETCH":
            return "OK", [(f"{args[0]} (BODY[] {{9}}".encode(), self.messages[int(args[0])]), b")"]
        self.seen.append(int(args[0]))
        return "OK", []


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[Inbox]:
    """The inbox every session opens, in place of a server."""
    kept = Inbox()

    class Session:
        def __init__(self, _door: ImapServer) -> None:
            pass

        def __enter__(self) -> Inbox:
            return kept

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(email_box, "_Session", Session)
    yield kept


async def test_the_first_pass_reads_nothing_and_later_ones_read_in_order_what_came_after(inbox: Inbox) -> None:
    """A mailbox is not made to answer its past; then each new message once, oldest first, marked read."""
    inbox.messages = {1: b"old", 2: b"old too"}
    first = await email_box.read_new(SERVER, Cursor())
    assert (first.messages, first.cursor) == ((), Cursor(7, 2))
    inbox.messages |= {4: b"four", 3: b"three"}
    second = await email_box.read_new(SERVER, first.cursor)
    assert (second.messages, second.cursor, inbox.seen) == (((3, b"three"), (4, b"four")), Cursor(7, 4), [3, 4])
    third = await email_box.read_new(SERVER, second.cursor)
    assert (third.messages, third.cursor) == ((), Cursor(7, 4)), "UID 4:* answers 4 again, which was read"


async def test_an_inbox_numbered_anew_is_taken_from_where_it_stands(inbox: Inbox) -> None:
    """Another UIDVALIDITY: its UIDs mean other messages, so nothing is read and the cursor starts again."""
    inbox.messages, inbox.validity = {9: b"nine"}, 8
    page = await email_box.read_new(SERVER, Cursor(7, 4))
    assert (page.messages, page.cursor) == ((), Cursor(8, 9))
