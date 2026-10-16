"""Rule 4, the schema: the models are the live schema (`alembic check` is empty), on the test database."""

import os
import subprocess

import pytest

from tests.conventions.canon import RUNTIME


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="alembic check needs the test database")
# On a fresh database `migrate up` runs the whole history first: minutes, not the suite's ten seconds.
@pytest.mark.timeout(300)
def test_models_are_the_schema() -> None:
    """`migrate up` brings the test database to this release; `alembic check` then finds nothing to add."""
    migrated = subprocess.run(
        ["pinecall-runtime", "migrate", "up"], cwd=RUNTIME, capture_output=True, text=True, check=False, timeout=300
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    ran = subprocess.run(["alembic", "check"], cwd=RUNTIME, capture_output=True, text=True, check=False, timeout=120)
    assert ran.returncode == 0, ran.stdout + ran.stderr
