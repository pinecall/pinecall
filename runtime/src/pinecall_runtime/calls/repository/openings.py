"""What a call is kept as when it opens, the configs it ran on, and the private values aside."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pinecall_runtime.calls.models import CallConfig, CallOpening, CallPrivate
from pinecall_runtime.kit.repository import Repository


class OpeningRepository(Repository[CallOpening]):
    """The first opening stands: a reopen says it again and changes nothing."""

    model = CallOpening

    async def keep(self, call: str, org: str, context: dict[str, Any], config_hash: str) -> None:
        """Keep the call's context and the hash of its config, once."""
        statement = insert(CallOpening).values(call=call, org=org, context=context, config_hash=config_hash)
        await self.session.execute(statement.on_conflict_do_nothing(index_elements=[CallOpening.call]))

    async def get(self, call: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """The context and the config the call opened with; None for one opened before it was kept."""
        statement = (
            select(CallOpening.context, CallConfig.config)
            .join(CallConfig, (CallConfig.org == CallOpening.org) & (CallConfig.hash == CallOpening.config_hash))
            .where(CallOpening.call == call)
        )
        row = (await self.session.execute(statement)).one_or_none()
        return None if row is None else (row[0], row[1])


class ConfigRepository(Repository[CallConfig]):
    """A resolved config, kept once per org under the hash of its JSON."""

    model = CallConfig

    async def keep(self, org: str, config_hash: str, config: dict[str, Any]) -> None:
        """Keep the config under its hash; one kept already stays."""
        statement = insert(CallConfig).values(org=org, hash=config_hash, config=config)
        await self.session.execute(statement.on_conflict_do_nothing(index_elements=[CallConfig.org, CallConfig.hash]))


class PrivateRepository(Repository[CallPrivate]):
    """One row per entry that held a private value: the values, sealed under the vault key."""

    model = CallPrivate

    async def keep(self, log: str, rows: Sequence[tuple[int, str]]) -> None:
        """Seal the private values of these entries of the log, by seq; one kept already stays."""
        if not rows:
            return
        statement = insert(CallPrivate).values([{"log": log, "seq": seq, "sealed": sealed} for seq, sealed in rows])
        await self.session.execute(statement.on_conflict_do_nothing(index_elements=[CallPrivate.log, CallPrivate.seq]))

    async def of_log(self, log: str) -> dict[int, str]:
        """Every sealed value of the log, by seq."""
        statement = select(CallPrivate.seq, CallPrivate.sealed).where(CallPrivate.log == log)
        return {int(seq): str(sealed) for seq, sealed in (await self.session.execute(statement)).all()}

    async def of_entry(self, log: str, seq: int) -> str | None:
        """The sealed value of one entry, or None when it kept none."""
        statement = select(CallPrivate.sealed).where(CallPrivate.log == log, CallPrivate.seq == seq)
        return (await self.session.execute(statement)).scalar_one_or_none()
