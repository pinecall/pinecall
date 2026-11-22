"""`local restore`: this machine's database replaced by a dump of another runtime's, to move one between machines."""

from pathlib import Path

from runtime.cli.setup import server
from runtime.cli.setup.compose import Compose, services_up
from runtime.cli.setup.env_file import EnvFile
from runtime.exceptions import ValidationError

# Every service that holds a connection to the database: stopped before its rows are replaced.
WRITERS = ("gateway", *server.RUNTIME_BESIDE_THE_GATEWAY)
# The schema emptied by its owner, who is the container's superuser here; the dump then makes its own
# extensions (`CREATE EXTENSION IF NOT EXISTS`) and every table, as the role this machine connects as.
EMPTY = ("psql", "-v", "ON_ERROR_STOP=1", "-U", "pinecall", "-d", "pinecall", "-c")
EMPTIED = "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION pinecall"
RESTORE = ("pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "-U", "pinecall", "-d", "pinecall")

STOP_FAILED = "docker compose could not stop the runtime before its database is replaced:\n{output}"
EMPTY_FAILED = "the database could not be emptied:\n{output}"
RESTORE_FAILED = "the dump was not restored, and the database is left as far as it got:\n{output}"


def replace_database(where: Path, dump: Path) -> None:
    """Stop what writes to the database, empty it, and restore the dump into it; the services stay stopped."""
    if not dump.is_file():
        raise ValidationError(f"{dump} is not a file: a dump made with `pg_dump -Fc`")
    values = EnvFile(where / "env").read()
    services_up(where, ("postgres",), values)
    if len(server.compose_files(where)) > 1:
        server.every_service(where, values).run("--progress", "quiet", "stop", *WRITERS, failed=STOP_FAILED)
    postgres = Compose((where / "compose.yaml",), environment=values)
    postgres.run("exec", "-T", "postgres", *EMPTY, EMPTIED, failed=EMPTY_FAILED)
    postgres.feed("exec", "-T", "postgres", *RESTORE, source=dump, failed=RESTORE_FAILED)
