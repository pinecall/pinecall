"""Every table says what it keeps and for whom, so nothing the box keeps can be left out of an erasure or an export."""

import importlib
from typing import Any, cast

from sqlalchemy import Column, Table

from runtime.kit.db import Kept, Model, Sealed
from tests.runtime.conventions.canon import DOMAINS, Module

# The columns that name whose a row is: each is named in the table's `Kept`, or the table says why it stays.
OWNERS = {"call": "call", "source_call": "call", "log": "call", "agent": "agent", "contact": "contact"}
# What a column the vault seals is called in this schema.
SEALED_NAMES = frozenset({"ciphertext"})


def _columns(model: type[Model]) -> list[Column[Any]]:
    table = model.__table__
    if not isinstance(table, Table):
        return []
    # SQLAlchemy types a table's columns as a collection of unknowns: read as untyped, then said.
    return cast(list[Column[Any]], list(cast(Any, table).columns))


def _mapped(modules: dict[str, Module]) -> list[type[Model]]:
    for domain in DOMAINS:
        if f"{domain}.models" in modules:
            importlib.import_module(f"runtime.{domain}.models")
    return [mapper.class_ for mapper in Model.registry.mappers]


def test_every_table_declares_what_it_keeps(modules: dict[str, Module]) -> None:
    """Each mapped class carries a `Kept`, and exports its columns or says why it exports none."""
    wrong: list[str] = []
    for model in _mapped(modules):
        kept = model.__dict__.get("__kept__")
        if not isinstance(kept, Kept):
            wrong.append(f"{model.__name__}: declares no `__kept__`")
        elif not kept.exported and not kept.not_exported:
            wrong.append(f"{model.__name__}: exports nothing and does not say why")
    assert not wrong, "\n".join(wrong)


def test_a_row_can_be_found_by_whose_it_is(modules: dict[str, Module]) -> None:
    """A column naming a call, an agent or a contact is named in `Kept`, an org's has the cascade, or the row stays."""
    wrong: list[str] = []
    for model in _mapped(modules):
        kept = model.__dict__.get("__kept__")
        if not isinstance(kept, Kept) or kept.outlives:
            continue
        for column in _columns(model):
            owner = OWNERS.get(column.name)
            if owner is not None and getattr(kept, owner) != column.name:
                wrong.append(f"{model.__name__}.{column.name}: names a {owner} that `Kept` does not")
            if column.name == "org" and not _goes_with_its_org(column):
                wrong.append(f"{model.__name__}.org: no cascade from orgs, and the table does not say it outlives")
    assert not wrong, "\n".join(wrong)


def test_what_the_vault_seals_is_typed_as_sealed(modules: dict[str, Module]) -> None:
    """A column of ciphertext is declared `Sealed`, so a rotation of the vault's key finds it."""
    wrong: list[str] = []
    for model in _mapped(modules):
        for column in _columns(model):
            if column.name in SEALED_NAMES and not isinstance(column.type, Sealed):
                wrong.append(f"{model.__name__}.{column.name}: sealed by the vault and not declared `Sealed`")
    assert not wrong, "\n".join(wrong)


def _goes_with_its_org(column: Column[Any]) -> bool:
    # By the key's own words, not its resolved column: the org's table may be a domain not imported here.
    return any(key.target_fullname == "orgs.id" and key.ondelete == "CASCADE" for key in column.foreign_keys)
