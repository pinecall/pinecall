"""Every table says what it keeps and for whom, so nothing the box keeps can be left out of an erasure or an export."""

import importlib
from typing import Any, cast

from sqlalchemy import Boolean, Column, Table

from runtime.kit.db import Kept, Model, Sealed
from tests.conventions.canon import DOMAINS, SRC, Module

# The columns that name whose a row is: each is named in the table's `Kept`, or the table says why it stays.
OWNERS = {"call": "call", "source_call": "call", "log": "call", "agent": "agent", "contact": "contact"}
# What a line of an export says of itself, and what its first line says for all of them: no column goes under these.
LINES_OWN = frozenset({"kind", "org", "env"})
# Where an erasure and an export call the owners' verbs the models name.
ERASURE = SRC / "retention" / "service" / "erasure.py"
EXPORT = SRC / "retention" / "service" / "export.py"
# What a column the vault seals is called in this schema. A log's `sealed` is a boolean, its seal having
# run: no ciphertext, and the one column of these names the vault never wrote.
SEALED_NAMES = frozenset({"ciphertext", "sealed", "sealed_key"})


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
    """A call, an agent or a contact a table names is named in `Kept`, an org's has the cascade, or the row stays."""
    wrong: list[str] = []
    for model in _mapped(modules):
        kept = model.__dict__.get("__kept__")
        if not isinstance(kept, Kept) or kept.outlives:
            continue
        # A table may name its call by two columns (`call_log` has `call` and `log`): `Kept` names one of them.
        named: dict[str, list[str]] = {}
        for column in _columns(model):
            if column.name in OWNERS:
                named.setdefault(OWNERS[column.name], []).append(column.name)
        for owner, names in named.items():
            if getattr(kept, owner) not in names:
                wrong.append(f"{model.__name__}: {', '.join(names)} name a {owner} that `Kept` does not")
        for column in _columns(model):
            if column.name == "org" and not _goes_with_its_org(column) and not kept.erased_by:
                wrong.append(
                    f"{model.__name__}.org: no cascade from orgs, no verb that erases it, no word that it stays"
                )
    assert not wrong, "\n".join(wrong)


def test_what_the_vault_seals_is_typed_as_sealed(modules: dict[str, Module]) -> None:
    """A column of ciphertext is declared `Sealed`, so a rotation of the vault's key finds it."""
    wrong: list[str] = []
    for model in _mapped(modules):
        for column in _columns(model):
            if column.name in SEALED_NAMES and not isinstance(column.type, Sealed | Boolean):
                wrong.append(f"{model.__name__}.{column.name}: sealed by the vault and not declared `Sealed`")
    assert not wrong, "\n".join(wrong)


# A row goes with its org when a cascading key ties it to `orgs.id`, or to the `org` of a parent that
# goes with its org (a file and a chunk go with their base, by a composite key, and the base with its
# org). By the key's own words, not its resolved column: the org's table may be a domain not imported here.
def _goes_with_its_org(column: Column[Any], seen: frozenset[str] = frozenset()) -> bool:
    for key in column.foreign_keys:
        if key.ondelete != "CASCADE":
            continue
        if key.target_fullname == "orgs.id":
            return True
        table, _, name = key.target_fullname.rpartition(".")
        parent = Model.metadata.tables.get(table)
        if name != "org" or parent is None or table in seen:
            continue
        if _goes_with_its_org(cast(Column[Any], cast(Any, parent).columns["org"]), seen | {table}):
            return True
    return False


def test_an_export_carries_columns_that_exist_under_keys_of_their_own(modules: dict[str, Module]) -> None:
    """Each exported column is the table's, and none goes under a key the line or the export's header says."""
    wrong: list[str] = []
    for model in _mapped(modules):
        kept = model.__dict__.get("__kept__")
        if not isinstance(kept, Kept):
            continue
        names = {column.name for column in _columns(model)}
        renamed = dict(kept.renamed)
        for column in kept.exported:
            if column not in names:
                wrong.append(f"{model.__name__}: exports `{column}`, which is no column of it")
            if renamed.get(column, column) in LINES_OWN:
                wrong.append(f"{model.__name__}: `{column}` would go under a key the line itself says: rename it")
        for column in renamed:
            if column not in kept.exported:
                wrong.append(f"{model.__name__}: renames `{column}`, which it does not export")
    assert not wrong, "\n".join(wrong)


def test_a_verb_a_table_names_exists_and_is_called(modules: dict[str, Module]) -> None:
    """The verb that erases a table's rows, or writes its lines, exists, and the erasure or the export calls it."""
    wrong: list[str] = []
    callers = {"erased_by": ERASURE.read_text(encoding="utf-8"), "exported_by": EXPORT.read_text(encoding="utf-8")}
    for model in _mapped(modules):
        kept = model.__dict__.get("__kept__")
        if not isinstance(kept, Kept):
            continue
        for field, caller in callers.items():
            named: str = getattr(kept, field)
            if not named:
                continue
            module, _, verb = named.rpartition(".")
            if not hasattr(importlib.import_module(f"runtime.{module}"), verb):
                wrong.append(f"{model.__name__}: `{field}` names {named}, which does not exist")
            elif f".{verb}(" not in caller:
                wrong.append(f"{model.__name__}: `{field}` names {named}, which retention never calls")
    assert not wrong, "\n".join(wrong)
