"""Every statement on the mail table: an org's mailbox."""

from typing import Any

from runtime.kit.repository import Repository
from runtime.mail.models import OrgMail


class MailRepository(Repository[OrgMail]):
    """An org's mailbox row."""

    model = OrgMail

    async def find(self, org: str) -> OrgMail | None:
        """The org's row, or None."""
        return await self.one_or_none(self.statement().where(OrgMail.org == org))

    async def put(self, org: str, values: dict[str, Any]) -> OrgMail:
        """Replace the org's row whole."""
        return await self.upsert({"org": org, **values}, key=["org"])
