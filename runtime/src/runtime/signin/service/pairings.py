"""Pairings: a terminal waiting for a browser to sign it in, the browser's approval, the key the terminal collects."""

import asyncio
import contextlib
import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.exceptions import Conflict, NotFound
from runtime.kit.commit import run_after_commit
from runtime.kit.crypto import Vault
from runtime.signal import Signal
from runtime.signin.service import codes
from runtime.signin.service.one_time import Kind, Minted, OneTimeSecrets

# A terminal waits ten minutes for its browser.
PAIRING = Kind("cli_", 600.0)


class NoSuchPairing(NotFound):
    """The code is no terminal's: one is collected once, and dies in ten minutes."""

    def __init__(self) -> None:
        super().__init__("no pairing answers to that: it was collected, it expired, or it never existed")


class AlreadyAnswered(Conflict):
    """A browser signed the terminal in already."""

    def __init__(self) -> None:
        super().__init__("that terminal is already signed in: it has a key waiting")


@dataclass(frozen=True, slots=True)
class WaitingTerminal:
    """A terminal waiting: what it calls itself, and the key a browser gave it once approved."""

    device: str | None = None
    key: str | None = None
    org: str | None = None


def _load_terminal(value: Mapping[str, Any]) -> WaitingTerminal:
    return WaitingTerminal(device=value.get("device"), key=value.get("key"), org=value.get("org"))


@dataclass(frozen=True, slots=True)
class Waiting:
    """A terminal as the browser about to sign it in reads it: its name, when its code dies, whether answered."""

    device: str | None
    expires_at: float
    answered: bool


@dataclass(frozen=True, slots=True)
class Approved:
    """A terminal signed in: what it calls itself, and the org its key opens."""

    device: str | None
    org: str
    org_name: str


class Pairings:
    """Terminals waiting for a browser to sign them in; the approval is heard on every gateway."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: Vault, signal: Signal) -> None:
        self.secrets = OneTimeSecrets(PAIRING, sessions, vault, load=_load_terminal, dump=asdict)
        self.signal = signal

    async def open(self, device: str | None) -> Minted:
        """The code a terminal prints, and when it dies."""
        return await self.secrets.mint(WaitingTerminal(device))

    async def get_status(self, code: str) -> Waiting:
        """The terminal and when its code dies, without spending; NoSuchPairing for a dead one."""
        kept = await self.secrets.read_alive(code)
        if kept is None:
            raise NoSuchPairing()
        return Waiting(kept.value.device, kept.expires_at, answered=kept.value.key is not None)

    async def collect(self, code: str, *, within_s: float = 0) -> str | None:
        """The key once, waiting up to `within_s` for an approval; None while nobody approved."""
        # Listening before the first look, so an approval between the two is heard.
        listener = await self.signal.subscribe(_approval_channel(code))
        try:
            key = await self._collect(code)
            if key is None and within_s > 0:
                with contextlib.suppress(TimeoutError, StopAsyncIteration):
                    async with asyncio.timeout(within_s):
                        await anext(listener)
                key = await self._collect(code)
            return key
        finally:
            listener.close()

    async def _collect(self, code: str) -> str | None:
        kept = await self.secrets.read_alive(code)
        if kept is None:
            raise NoSuchPairing()
        if kept.value.key is None:
            return None
        spent = await self.secrets.spend(code)
        if spent is None or spent.key is None:
            raise NoSuchPairing()
        return spent.key


# The key is written under the terminal's code in the transaction that mints it, and every gateway is
# told once that is committed: a terminal told before would collect a key whose row is not there yet.
async def approve(session: AsyncSession, pairings: Pairings, code: str, actor: Actor) -> Approved:
    """Sign the terminal in as the person this browser is; the terminal gets a key of its own."""
    kept = await pairings.secrets.read_alive(code)
    if kept is None:
        raise NoSuchPairing()
    if kept.value.key is not None:
        raise AlreadyAnswered()
    issued = await codes.another_device_key(session, actor, device=kept.value.device)
    answered = replace(kept.value, key=issued.secret, org=issued.org)
    if not await pairings.secrets.fill_on(session, code, answered):
        raise AlreadyAnswered()
    run_after_commit(session, lambda: pairings.signal.publish(_approval_channel(code), b""))
    org = await accounts.find_org(session, issued.org)
    return Approved(kept.value.device, issued.org, issued.org if org is None else org.name)


# The code is the terminal's secret: the channel every gateway hears is its hash.
def _approval_channel(code: str) -> str:
    return f"pairing:{hashlib.sha256(code.encode()).hexdigest()}"
