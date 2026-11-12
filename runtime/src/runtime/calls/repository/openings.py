"""The call_openings rows and the call_configs they name: what a call is, kept when it opens."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from runtime.calls.models import CallConfig, CallOpening
from runtime.kit.repository import Repository


@dataclass(frozen=True, slots=True)
class KeptOpening:
    """An opening as its rows hold it: the context and the declaration, each as the JSON it was kept as."""

    context: dict[str, Any]
    config: dict[str, Any]


# One repository for the two tables: an opening is never read without its config, and a config is
# never kept but for an opening. Until 2026-11 they were two classes, called one after the other.
class OpeningRepository(Repository[CallOpening]):
    """The first opening stands: a reopen says it again and changes nothing."""

    model = CallOpening

    async def keep(self, call: str, org: str, context: dict[str, Any], hashed: str, config: dict[str, Any]) -> None:
        """Keep the config under its hash, once per org, and the call's context with that hash, once."""
        kept = insert(CallConfig).values(org=org, hash=hashed, config=config)
        await self.session.execute(kept.on_conflict_do_nothing(index_elements=[CallConfig.org, CallConfig.hash]))
        opening = insert(CallOpening).values(call=call, org=org, context=context, config_hash=hashed)
        await self.session.execute(opening.on_conflict_do_nothing(index_elements=[CallOpening.call]))

    async def find(self, call: str) -> KeptOpening | None:
        """The context and the config the call opened with; None for one opened before it was kept."""
        statement = (
            select(CallOpening.context, CallConfig.config)
            .join(CallConfig, (CallConfig.org == CallOpening.org) & (CallConfig.hash == CallOpening.config_hash))
            .where(CallOpening.call == call)
        )
        row = (await self.session.execute(statement)).one_or_none()
        return None if row is None else KeptOpening(context=row[0], config=row[1])
