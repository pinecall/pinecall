"""The box's brand: what its pages and emails are called and painted with."""

import logging
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import ValidationError
from runtime.platform.service.settings import Setting, find_setting, put_setting

logger = logging.getLogger(__name__)

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


def _load(value: Mapping[str, Any]) -> Brand:
    logo = value.get("logo_url")
    return Brand(
        name=str(value.get("name") or NAME),
        logo_url=str(logo) if logo else None,
        accent=str(value.get("accent") or ACCENT),
    )


BRAND: Setting[Brand] = Setting("brand", _load, asdict)


async def get_brand(session: AsyncSession) -> Brand:
    """The box's brand; Pinecall's when nobody set one, or when the row does not read."""
    try:
        return await find_setting(session, BRAND) or Brand()
    except ValidationError:
        logger.warning("the box's brand does not read: emails go out as Pinecall's")
        return Brand()


async def put_brand(session: AsyncSession, brand: Brand) -> None:
    """Keep the box's brand."""
    await put_setting(session, BRAND, brand)


# None keeps a field; an empty string sets it back to the default, the one way to clear a logo.
def change_brand(
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
