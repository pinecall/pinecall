"""An org's own mailbox: IMAP to read what is written to it, SMTP to answer from it; on no trunk, no call out."""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import formataddr
from typing import Any, ClassVar, Self, override

import httpx

from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, UpstreamError, ValidationError
from runtime.kit.text import parse_email
from runtime.mail import service as mail
from runtime.telephony.models import CarrierKind
from runtime.telephony.service import email_box
from runtime.telephony.service.carrier import (
    Carrier,
    Outbound,
    Owned,
    SipNames,
    Step,
    read_optional_text,
    read_text,
)
from runtime.telephony.service.fence import Fenced
from runtime.telephony.service.networks import Standing
from runtime.wire.worker import LegTrunk

KIND = "email"
IMAP_PORT = 993
SMTP_PORT = 465
# The port SMTP is spoken over TLS from the first byte; any other is upgraded with STARTTLS (587).
IMPLICIT_TLS = 465


def _read_port(account: Mapping[str, object], name: str, default: int) -> int:
    value = account.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} is not a port")
    return value


@dataclass(frozen=True, slots=True)
class EmailAccount(Carrier):
    """A mailbox of the org's: its address, where it is read and where it sends from, and the logins to both."""

    kind: ClassVar[CarrierKind] = CarrierKind.email
    name: ClassVar[str] = "your mail server"
    has_api: ClassVar[bool] = False
    channel: ClassVar[Channel] = Channel.email

    org: str
    address: str
    password: str
    imap_host: str
    smtp_host: str
    # The IMAP login; the address when it is the same.
    username: str = ""
    imap_port: int = IMAP_PORT
    smtp_port: int = SMTP_PORT
    # SMTP's own login when it is another than IMAP's: a relay's, such as Amazon SES's.
    smtp_username: str = ""
    smtp_password: str = ""
    # The name the contact reads beside the address.
    sender_name: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        # The SMTP side is checked as the box's own mailboxes are: a bare host, a port.
        _ = self.outbox
        if not 1 <= self.imap_port <= 65535:
            raise ValidationError(f"an IMAP port is 1 to 65535, not {self.imap_port}")

    @property
    @override
    def id(self) -> str:
        """The address."""
        return self.address

    @property
    def login(self) -> str:
        """The IMAP login."""
        return self.username or self.address

    @property
    def imap(self) -> email_box.ImapServer:
        """The IMAP side, where what is written to the address is read."""
        return email_box.ImapServer(self.imap_host, self.imap_port, self.login, self.password)

    @property
    def outbox(self) -> mail.Mailbox:
        """The SMTP side as the mail domain sends through it, the contact reading the name and the address."""
        return mail.Mailbox(
            host=self.smtp_host,
            port=self.smtp_port,
            security="tls" if self.smtp_port == IMPLICIT_TLS else "starttls",
            username=self.smtp_username or self.login,
            password=self.smtp_password or self.password,
            sender=formataddr((self.sender_name, self.address)) if self.sender_name else self.address,
        )

    @classmethod
    @override
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The mailbox out of what a row seals or a body brings."""
        try:
            address = parse_email(read_text(account, "address"))
        except ValidationError as wrong:
            raise ValueError(wrong.message) from None
        return cls(
            org=org,
            address=address,
            password=read_text(account, "password"),
            imap_host=read_text(account, "imap_host"),
            smtp_host=read_text(account, "smtp_host"),
            username=read_optional_text(account, "username") or "",
            imap_port=_read_port(account, "imap_port", IMAP_PORT),
            smtp_port=_read_port(account, "smtp_port", SMTP_PORT),
            smtp_username=read_optional_text(account, "smtp_username") or "",
            smtp_password=read_optional_text(account, "smtp_password") or "",
            sender_name=read_optional_text(account, "sender_name") or "",
            label=read_optional_text(account, "label") or "",
        )

    @override
    def dump(self) -> dict[str, Any]:
        """The mailbox as its row seals it."""
        account = {"kind": KIND, **{name: getattr(self, name) for name in _FIELDS}}
        return {"account": account, "outbound": None}

    # A password is changed far more often than a relay: bringing the mailbox again with no SMTP password
    # keeps the one it had for the same SMTP login.
    @override
    def keep_from(self, was: object) -> Self:
        """The mailbox as brought, with the SMTP password it had when it brings none for the same login."""
        if self.smtp_password or not isinstance(was, EmailAccount) or was.smtp_username != self.smtp_username:
            return self
        return dataclasses.replace(self, smtp_password=was.smtp_password)

    # Both doors are tried as the inbox and the replies will use them: a login either refuses is said
    # here, in the server's words, and not on the first email.
    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse a mailbox whose IMAP or SMTP login the server refuses."""
        try:
            await email_box.check_inbox(self.imap)
            mail.check_public(self.outbox)
            await mail.check_login(self.outbox)
        except UpstreamError as refused:
            raise ValidationError(f"{self.address} cannot be read and answered: {refused.message}") from refused

    @override
    def calling_networks(self) -> tuple[str, ...] | None:
        """None: an email comes over no trunk."""
        return None

    @override
    def fence(self, number: str, standing: Standing) -> Fenced:
        """Refused: a mailbox is on no SIP trunk."""
        raise ValidationError(f"{self.id} is a mailbox: it is on no SIP trunk")

    @override
    def list_missing_to_dial(self) -> list[str]:
        """Everything: it places no call."""
        return [f"{self.id} is a mailbox: it places no call"]

    @override
    def leg_trunk(self, shown: str) -> LegTrunk:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """The one address the mailbox is."""
        return [Owned(number=self.address, name=self.sender_name or self.address)]

    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """The address is the mailbox's own, and it answers email alone."""
        if channel is not Channel.email:
            raise ValidationError(f"{self.address} is a mailbox: it answers email, not {channel}")
        if number != self.address:
            raise ValidationError(f"{number} is not the mailbox's address: the account is {self.address}")

    @override
    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """Nothing: the box reads the inbox itself, and points nothing at it."""
        return []

    @override
    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """None: nothing is pointed anywhere."""
        return None

    @override
    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    @override
    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])


# What a row seals, beside its kind.
_FIELDS = (
    "address",
    "password",
    "imap_host",
    "smtp_host",
    "username",
    "imap_port",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "sender_name",
    "label",
)
