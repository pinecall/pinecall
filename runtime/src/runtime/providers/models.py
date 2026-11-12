"""The providers tables: provider_keys, org_telemetry."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, Sealed, utc_now


class ProviderKey(Model):
    """One row per org and vendor: the org's own credentials for it, sealed."""

    __tablename__ = "provider_keys"
    __kept__ = Kept(exported=("vendor", "set_at"))

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    vendor: Mapped[str] = mapped_column(Text, primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Sealed, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


# No foreign key reaches the row from its org (`org` is text): until 2026-11 an org erased left its
# collector and the sealed headers behind. The org's erasure calls `forget_telemetry`.
class OrgTelemetry(Model):
    """The endpoint in clear, the headers sealed, and whether a span may carry PII."""

    __tablename__ = "org_telemetry"
    __kept__ = Kept(
        exported=("endpoint", "pii", "set_at"),
        erased_by="providers.service.telemetry.forget_telemetry",
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Sealed)
    pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
