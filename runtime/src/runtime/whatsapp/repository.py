"""The whatsapp_seen table: the message ids Meta delivered, claimed by one delivery and read once."""

from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert

from runtime.kit.repository import Repository
from runtime.whatsapp.models import WhatsappSeen


class WhatsappSeenRepository(Repository[WhatsappSeen]):
    """The message ids Meta delivered, claimed by one delivery and read once."""

    model = WhatsappSeen

    async def find(self, org: str, message_id: str) -> WhatsappSeen | None:
        """The row of the message, or None."""
        return await self.one_or_none(
            self.statement().where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
        )

    # The insert is the check, in one statement: of two deliveries at once, one inserts and the
    # other finds the row; a claim left unread past its lease is taken over in the same statement.
    async def claim(self, org: str, message_id: str, *, at: datetime, stale_before: datetime) -> bool:
        """Claim the message for this delivery; False when another read it or is reading it."""
        statement = insert(WhatsappSeen).values(org=org, message_id=message_id, claimed_at=at)
        claimed = statement.on_conflict_do_update(
            index_elements=[WhatsappSeen.org, WhatsappSeen.message_id],
            set_={"claimed_at": statement.excluded.claimed_at},
            where=(WhatsappSeen.read_at.is_(None)) & (WhatsappSeen.claimed_at < stale_before),
        ).returning(WhatsappSeen.org)
        return (await self.session.execute(claimed)).scalar_one_or_none() is not None

    async def mark_read(self, org: str, message_id: str, *, at: datetime) -> None:
        """The claimed message is read: every later delivery of it is dropped."""
        await self.session.execute(
            update(WhatsappSeen)
            .where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
            .values(read_at=at)
        )

    async def release(self, org: str, message_id: str) -> None:
        """Give up the claim of a message whose reading failed, so Meta's next delivery reads it."""
        await self.session.execute(
            delete(WhatsappSeen).where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
        )

    async def delete_before(self, before: datetime) -> int:
        """Forget the message ids claimed before the moment; how many. Run box-wide by the caller."""
        return await self.change(delete(WhatsappSeen).where(WhatsappSeen.claimed_at < before))
