"""Alembic's environment: the models are the schema; the URL is the settings'."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Every domain's tables: a model is on the metadata once its module ran, so each is imported here,
# and `alembic check` finds a table the metadata lacks only when a domain's models are left out.
from pinecall_runtime.accounts import models as accounts_models
from pinecall_runtime.agents import models as agents_models
from pinecall_runtime.alerts import models as alerts_models
from pinecall_runtime.billing import models as billing_models
from pinecall_runtime.calls import models as calls_models
from pinecall_runtime.channels import models as channels_models
from pinecall_runtime.compliance import models as compliance_models
from pinecall_runtime.config import load_settings
from pinecall_runtime.evals import models as evals_models
from pinecall_runtime.fleet import models as fleet_models
from pinecall_runtime.hosting import models as hosting_models
from pinecall_runtime.judging import models as judging_models
from pinecall_runtime.kit.db import Model
from pinecall_runtime.knowledge import models as knowledge_models
from pinecall_runtime.platform import models as platform_models
from pinecall_runtime.providers import models as providers_models
from pinecall_runtime.retention import models as retention_models
from pinecall_runtime.telephony import models as telephony_models

TABLES = (
    accounts_models,
    agents_models,
    alerts_models,
    billing_models,
    calls_models,
    channels_models,
    compliance_models,
    evals_models,
    fleet_models,
    hosting_models,
    judging_models,
    knowledge_models,
    platform_models,
    providers_models,
    retention_models,
    telephony_models,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Model.metadata

# What the runtime declares but Alembic must not try to manage: the day partitions of call_log
# (made by the retention task), the first partition and the default one, and its own table.
UNMANAGED = {"schema_migrations", "call_log_before_the_days", "call_log_default"}
EXTENSION_INDEXES = ("_hnsw", "_bm25")


def include_object(_obj: object, name: str | None, type_: str, _reflected: bool, _compare_to: object) -> bool:
    """Skip the partitions, the old runner's bookkeeping, and the extensions' indexes."""
    if type_ == "table" and name is not None:
        return name not in UNMANAGED and not name.startswith("call_log_2")
    # pgvector's hnsw and pg_textsearch's bm25 indexes: made by the history, beyond what Alembic renders.
    if type_ == "index" and name is not None:
        return not name.endswith(EXTENSION_INDEXES)
    return True


def run_migrations_offline() -> None:
    """Emit SQL without a connection."""
    context.configure(
        url=load_settings().database_dsn("psycopg"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run against the settings' database."""
    engine = create_async_engine(load_settings().database_dsn(), poolclass=None)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()
    # The connection's transport closes on the loop's next turn; `asyncio.run` would close the loop
    # first and leave the socket open, which the test suite reports as a ResourceWarning.
    await asyncio.sleep(0)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
