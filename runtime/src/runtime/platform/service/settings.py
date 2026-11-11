"""A named value of the box: declared once with how it reads, then found, put and deleted by its declaration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.platform.repository.settings import BoxSettingRepository


# The table is one JSON value per name. A domain declares each of its settings once, with the two
# functions that read and write its value, so no caller meets an untyped dict or spells a name twice.
@dataclass(frozen=True, slots=True)
class Setting[T]:
    """One named value of the box: its name, how its JSON is read, and how it is written."""

    name: str
    load: Callable[[Mapping[str, Any]], T]
    dump: Callable[[T], dict[str, Any]]


async def find_setting[T](session: AsyncSession, setting: Setting[T]) -> T | None:
    """The setting's value, or None when nobody set it."""
    row = await BoxSettingRepository(session).find(setting.name)
    return None if row is None else setting.load(row.value)


async def find_sealed_setting[T](session: AsyncSession, setting: Setting[T]) -> tuple[T, str] | None:
    """The setting's value and the secret sealed beside it; None when no secret is kept."""
    row = await BoxSettingRepository(session).find(setting.name)
    return None if row is None or row.ciphertext is None else (setting.load(row.value), row.ciphertext)


async def list_settings[T](session: AsyncSession, setting: Setting[T]) -> dict[str, T]:
    """Every value kept under names that begin with the setting's, by name."""
    rows = await BoxSettingRepository(session).list_under(setting.name)
    return {row.name: setting.load(row.value) for row in rows}


async def put_setting[T](
    session: AsyncSession, setting: Setting[T], value: T, *, ciphertext: str | None = None
) -> None:
    """Set the value whole; a secret part of it sealed beside it."""
    await BoxSettingRepository(session).put(setting.name, setting.dump(value), ciphertext)


async def put_setting_if_absent[T](session: AsyncSession, setting: Setting[T], value: T) -> bool:
    """Set the value only where nobody set one; whether it was set."""
    return await BoxSettingRepository(session).put_if_absent(setting.name, setting.dump(value))


async def delete_setting[T](session: AsyncSession, setting: Setting[T]) -> bool:
    """Forget the setting; whether there was one."""
    return await BoxSettingRepository(session).delete_named(setting.name)
