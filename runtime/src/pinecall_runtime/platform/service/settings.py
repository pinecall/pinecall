"""The box's own settings: the brand its pages and emails carry, and the generic named value."""

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.platform.repository import BoxSettingRepository, ReplicationRepository

logger = logging.getLogger(__name__)

BRAND = "brand"
NAME = "Pinecall"
ACCENT = "#5b3df5"
A_BRAND_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
LONGEST_NAME = 60


@dataclass(frozen=True, slots=True)
class Brand:
    """What the box's emails and pages are called and painted with."""

    name: str = NAME
    logo_url: str | None = None
    accent: str = ACCENT

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > LONGEST_NAME or "\n" in self.name:
            raise ValidationError(f"a brand's name is one line of at most {LONGEST_NAME} characters")
        if not A_BRAND_COLOUR.match(self.accent):
            raise ValidationError(f"{self.accent!r} is not an accent: a colour is #rrggbb")
        if self.logo_url is not None and not _is_https_url(self.logo_url):
            raise ValidationError(f"{self.logo_url!r} is not a logo: an https:// URL of an image")


async def get_setting(session: AsyncSession, name: str) -> dict[str, Any] | None:
    """The setting's value, or None when the operator never set it."""
    row = await BoxSettingRepository(session).get(name)
    return None if row is None else row.value


async def put_setting(
    session: AsyncSession, name: str, value: dict[str, Any], *, ciphertext: str | None = None
) -> None:
    """Set the value whole; a secret part of it sealed beside it."""
    await BoxSettingRepository(session).put(name, value, ciphertext)


async def put_setting_if_absent(session: AsyncSession, name: str, value: dict[str, Any]) -> bool:
    """Set the value only where nobody set one; whether it was set."""
    return await BoxSettingRepository(session).put_if_absent(name, value)


async def get_sealed_setting(session: AsyncSession, name: str) -> tuple[dict[str, Any], str] | None:
    """The setting's value and the secret sealed beside it; None when there is no secret kept."""
    row = await BoxSettingRepository(session).get(name)
    return None if row is None or row.ciphertext is None else (row.value, row.ciphertext)


async def delete_setting(session: AsyncSession, name: str) -> bool:
    """Forget the setting; whether there was one."""
    return await BoxSettingRepository(session).remove(name)


async def get_brand(session: AsyncSession) -> Brand:
    """The box's brand; Pinecall's when nobody set one, or when the row does not read."""
    value = await get_setting(session, BRAND)
    if value is None:
        return Brand()
    logo = value.get("logo_url")
    try:
        return Brand(
            name=str(value.get("name") or NAME),
            logo_url=str(logo) if logo else None,
            accent=str(value.get("accent") or ACCENT),
        )
    except ValidationError:
        logger.warning("the box's brand does not read: emails go out as Pinecall's")
        return Brand()


async def put_brand(session: AsyncSession, brand: Brand) -> None:
    """Keep the box's brand."""
    await put_setting(session, BRAND, {"name": brand.name, "logo_url": brand.logo_url, "accent": brand.accent})


# None keeps a field; an empty string sets it back to the default, the one way to clear a logo.
def changed_brand(
    brand: Brand, *, name: str | None = None, logo_url: str | None = None, accent: str | None = None
) -> Brand:
    """The brand with what was named replaced."""
    return Brand(
        name=brand.name if name is None else (name.strip() or NAME),
        logo_url=brand.logo_url if logo_url is None else (logo_url.strip() or None),
        accent=brand.accent if accent is None else (accent.strip().lower() or ACCENT),
    )


def _is_https_url(written: str) -> bool:
    parts = urlsplit(written)
    return parts.scheme == "https" and bool(parts.hostname) and not any(c in written for c in " \"'<>\n")


async def replica_lags(session: AsyncSession) -> list[tuple[str, float]]:
    """How far behind each standby of the database is, in seconds, by its name."""
    return await ReplicationRepository(session).lags()
