"""The box_settings table: one JSON value per name."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from runtime.kit.repository import Repository
from runtime.kit.time import now
from runtime.platform.models import BoxSetting


class BoxSettingRepository(Repository[BoxSetting]):
    """Named settings of the box."""

    model = BoxSetting

    async def find(self, name: str) -> BoxSetting | None:
        """The row by name, or None."""
        return await self.one_or_none(self.statement().where(BoxSetting.name == name))

    async def list_under(self, prefix: str) -> Sequence[BoxSetting]:
        """Every row whose name begins with the prefix, by name."""
        named = BoxSetting.name.startswith(prefix, autoescape=True)
        return await self.all(self.statement().where(named).order_by(BoxSetting.name))

    async def put(self, name: str, value: dict[str, Any], ciphertext: str | None = None) -> BoxSetting:
        """Set the value whole; the ciphertext beside it where part of the value is a secret."""
        values = {"name": name, "value": value, "ciphertext": ciphertext, "set_at": now()}
        return await self.upsert(values, key=["name"])

    # One statement, so two processes seeding at once never both think they were first.
    async def put_if_absent(self, name: str, value: dict[str, Any]) -> bool:
        """Set the value only where nobody set one; whether it was set."""
        statement = (
            insert(BoxSetting)
            .values(name=name, value=value, set_at=now())
            .on_conflict_do_nothing(index_elements=[BoxSetting.name])
            .returning(BoxSetting.name)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def delete_named(self, name: str) -> bool:
        """Forget the setting; whether there was one."""
        row = await self.find(name)
        if row is None:
            return False
        await self.delete(row)
        return True
