"""The provider_keys table, and the box's own vendor credentials among its settings."""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert

from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now
from pinecall_runtime.platform.models import BoxSetting
from pinecall_runtime.providers.models import ProviderKey

# The box's own credentials sit beside its other settings, one row per vendor.
BOX_CREDENTIALS = "credentials/"


class ProviderKeyRepository(Repository[ProviderKey]):
    """An org's own credentials per vendor, sealed."""

    model = ProviderKey

    async def of_org(self, org: str) -> Sequence[ProviderKey]:
        """Every vendor the org keyed, by name."""
        return await self.all(self.statement().where(ProviderKey.org == org).order_by(ProviderKey.vendor))

    async def get(self, org: str, vendor: str) -> ProviderKey | None:
        """The org's row for the vendor."""
        return await self.one_or_none(self.statement().where(ProviderKey.org == org, ProviderKey.vendor == vendor))

    # One statement, so two admins keying the vendor at once leave the last one's, never an error.
    async def put(self, org: str, vendor: str, ciphertext: str) -> None:
        """Keep the sealed credentials, replacing any the org had for the vendor."""
        statement = insert(ProviderKey).values(org=org, vendor=vendor, ciphertext=ciphertext, set_at=now())
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[ProviderKey.org, ProviderKey.vendor],
                set_={"ciphertext": statement.excluded.ciphertext, "set_at": statement.excluded.set_at},
            )
        )

    async def drop(self, org: str, vendor: str) -> bool:
        """Forget the org's credentials for the vendor; whether it had any."""
        row = await self.get(org, vendor)
        if row is None:
            return False
        await self.delete(row)
        return True


class BoxCredentialRepository(Repository[BoxSetting]):
    """The box's own credentials: the `credentials/<vendor>` rows of box_settings."""

    model = BoxSetting

    async def all_vendors(self) -> Sequence[BoxSetting]:
        """Every vendor the box holds a key for, by name."""
        return await self.all(
            self.statement()
            .where(BoxSetting.name.startswith(BOX_CREDENTIALS), BoxSetting.ciphertext.is_not(None))
            .order_by(BoxSetting.name)
        )

    # One statement, as an org's own: two operators keying the vendor at once leave the last one's.
    async def put(self, vendor: str, ciphertext: str) -> None:
        """Keep the box's sealed credentials for the vendor."""
        name = f"{BOX_CREDENTIALS}{vendor}"
        statement = insert(BoxSetting).values(name=name, value={}, ciphertext=ciphertext, set_at=now())
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[BoxSetting.name],
                set_={"ciphertext": statement.excluded.ciphertext, "set_at": statement.excluded.set_at},
            )
        )

    async def drop(self, vendor: str) -> bool:
        """Stop holding the vendor's key; whether the box held one."""
        row = await self.one_or_none(self.statement().where(BoxSetting.name == f"{BOX_CREDENTIALS}{vendor}"))
        if row is None:
            return False
        await self.delete(row)
        return True


def vendor_of(row: BoxSetting) -> str:
    """The vendor a `credentials/<vendor>` row is for."""
    return row.name.removeprefix(BOX_CREDENTIALS)
