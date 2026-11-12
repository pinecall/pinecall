"""Every statement on the providers tables, and the listing of the box's own credentials among its settings."""

from collections.abc import Sequence

from sqlalchemy import delete

from runtime.kit.repository import Repository
from runtime.kit.time import now
from runtime.platform.models import BoxSetting
from runtime.providers.models import OrgTelemetry, ProviderKey

# The box's own credentials sit beside its other settings, one row per vendor.
BOX_CREDENTIALS = "credentials/"


class ProviderKeyRepository(Repository[ProviderKey]):
    """An org's own credentials per vendor, sealed."""

    model = ProviderKey

    async def list_of_org(self, org: str) -> Sequence[ProviderKey]:
        """Every vendor the org keyed, by name."""
        return await self.all(self.statement().where(ProviderKey.org == org).order_by(ProviderKey.vendor))

    async def list_of_vendor(self, vendor: str) -> Sequence[ProviderKey]:
        """Every org's row for the vendor. Read box-wide by the caller."""
        return await self.all(self.statement().where(ProviderKey.vendor == vendor).order_by(ProviderKey.org))

    # One statement, so two admins keying the vendor at once leave the last one's, never an error.
    async def put(self, org: str, vendor: str, ciphertext: str) -> ProviderKey:
        """Keep the sealed credentials, replacing any the org had for the vendor."""
        values = {"org": org, "vendor": vendor, "ciphertext": ciphertext, "set_at": now()}
        return await self.upsert(values, key=["org", "vendor"])

    async def delete_of(self, org: str, vendor: str) -> bool:
        """Forget the org's credentials for the vendor; whether it had any."""
        statement = delete(ProviderKey).where(ProviderKey.org == org, ProviderKey.vendor == vendor)
        return await self.change(statement) > 0


# The rows are platform's table and are written through its settings; what its settings do not answer
# is every sealed row under one prefix, which is read here.
class BoxCredentialRepository(Repository[BoxSetting]):
    """The box's own credentials: the `credentials/<name>` rows of box_settings."""

    model = BoxSetting

    async def list_sealed(self) -> Sequence[BoxSetting]:
        """Every name the box holds sealed credentials under, by name."""
        return await self.all(
            self.statement()
            .where(BoxSetting.name.startswith(BOX_CREDENTIALS, autoescape=True), BoxSetting.ciphertext.is_not(None))
            .order_by(BoxSetting.name)
        )


class TelemetryRepository(Repository[OrgTelemetry]):
    """One row per org: where its calls' traces go."""

    model = OrgTelemetry

    async def find(self, org: str) -> OrgTelemetry | None:
        """The org's telemetry row, or None when its traces go nowhere."""
        return await self.one_or_none(self.statement().where(OrgTelemetry.org == org))

    async def put(self, org: str, *, endpoint: str, ciphertext: str | None, pii: bool) -> OrgTelemetry:
        """Keep where the org's traces go, replacing what it had."""
        values = {"org": org, "endpoint": endpoint, "ciphertext": ciphertext, "pii": pii, "set_at": now()}
        return await self.upsert(values, key=["org"])

    async def delete_of_org(self, org: str) -> bool:
        """Forget where the org's traces went; whether they went anywhere."""
        return await self.change(delete(OrgTelemetry).where(OrgTelemetry.org == org)) > 0
