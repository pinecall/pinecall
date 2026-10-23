"""The box's own keys a runtime runs on, drawn into its env file once, and again when its database forgot them."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.postgres import session_maker

# The box's own keys of the sandbox, drawn into the env file: its fleet's, and its runner's. A key
# the database does not know (deleted with `down --volumes`, the env file kept) is drawn again.
BOX_KEYS = (
    ("PINECALL_WORKER_KEY", KeyScope.fleet, Env.sandbox, "the sandbox fleet"),
    ("PINECALL_RUNNER_KEY", KeyScope.runner, Env.sandbox, "the sandbox runner"),
)
# A server's production fleet too: its worker answers production's calls.
PRODUCTION_FLEET_KEY = ("PINECALL_PRODUCTION_WORKER_KEY", KeyScope.fleet, Env.production, "the production fleet")


async def draw_box_keys(
    engine: AsyncEngine, values: dict[str, str], env: Path, *, production_fleet: bool = False
) -> None:
    """Each box key missing from the env file, or one its database does not know, drawn and written."""
    wanted = (*BOX_KEYS, PRODUCTION_FLEET_KEY) if production_fleet else BOX_KEYS
    async with session_maker(engine).begin() as session:
        for variable, scope, key_env, label in wanted:
            if variable in values and await keys.verify_key(session, values[variable]) is not None:
                continue
            issue = keys.Issue(org=DEFAULT_ORG, env=key_env, scopes=frozenset({scope}), label=label)
            _, secret = await keys.issue_key(session, issue)
            write_variable(env, values, variable, secret)


def write_variable(env: Path, values: dict[str, str], variable: str, value: str) -> None:
    """The variable's line in the env file, replaced or added, and the value in the settings."""
    values[variable] = value
    kept = [line for line in env.read_text(encoding="utf-8").splitlines() if not line.startswith(f"{variable}=")]
    env.write_text("".join(f"{line}\n" for line in [*kept, f"{variable}={value}"]), encoding="utf-8")
