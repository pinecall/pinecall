"""The org_policy table: an org's policy, one row."""

from typing import Any

from runtime.compliance.models import OrgPolicy
from runtime.kit.repository import Repository
from runtime.kit.time import now


class PolicyRepository(Repository[OrgPolicy]):
    """One row per org; an org without one has the platform's defaults."""

    model = OrgPolicy

    async def find(self, org: str) -> OrgPolicy | None:
        """The org's policy row, or None when nobody set one."""
        return await self.one_or_none(self.statement().where(OrgPolicy.org == org))

    async def put(self, org: str, values: dict[str, Any], *, by: str) -> OrgPolicy:
        """Replace the org's policy whole, and write down who did."""
        return await self.upsert({"org": org, **values, "set_by": by, "set_at": now()}, key=["org"])
