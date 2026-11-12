"""The models are the schema: against the database the migrations made, Alembic would generate nothing."""

from sqlalchemy.ext.asyncio import AsyncEngine

from runtime.platform.service.schema import find_drift
from tests.conftest import needs_the_database


# A table, a column or an index a model declares and no revision makes is a statement that fails on
# the first request that reaches it. The fixture is asked for the database it migrated.
@needs_the_database
def test_the_models_are_the_schema(engine: AsyncEngine) -> None:
    """`alembic check` finds no difference between the models and the migrated database."""
    del engine
    drift = find_drift()
    assert drift is None, drift
