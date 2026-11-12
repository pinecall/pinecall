"""Alembic's environment: the models are the schema; the URL is the settings'."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Every domain's tables: a model is on the metadata once its module ran, so each is imported here,
# and `alembic check` finds a table the metadata lacks only when a domain's models are left out.
from runtime.accounts import models as accounts_models
from runtime.agents import models as agents_models
from runtime.alerts import models as alerts_models
from runtime.billing import models as billing_models
from runtime.calls import models as calls_models
from runtime.compliance import models as compliance_models
from runtime.config import load_settings
from runtime.evals import models as evals_models
from runtime.fleet import models as fleet_models
from runtime.flows import models as flows_models
from runtime.hosting import models as hosting_models
from runtime.insights import models as insights_models
from runtime.judging import models as judging_models
from runtime.kit.db import Model
from runtime.knowledge import models as knowledge_models
from runtime.live import models as live_models
from runtime.mail import models as mail_models
from runtime.platform import models as platform_models
from runtime.providers import models as providers_models
from runtime.retention import models as retention_models
from runtime.signin import models as signin_models
from runtime.telephony import models as telephony_models
from runtime.whatsapp import models as whatsapp_models

TABLES = (
    accounts_models,
    agents_models,
    alerts_models,
    billing_models,
    calls_models,
    compliance_models,
    evals_models,
    fleet_models,
    flows_models,
    hosting_models,
    insights_models,
    judging_models,
    knowledge_models,
    live_models,
    mail_models,
    platform_models,
    providers_models,
    retention_models,
    signin_models,
    telephony_models,
    whatsapp_models,
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
