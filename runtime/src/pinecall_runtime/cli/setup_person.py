"""Who `setup` makes: the console's admin, and this machine signed in to its own runtime as the CLI keeps a sign-in."""

import json
import os
from collections.abc import Mapping
from pathlib import Path

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys, members, orgs
from pinecall_runtime.cli import local
from pinecall_runtime.cli import orgs as orgs_cli
from pinecall_runtime.cli import setup_ask as ask
from pinecall_runtime.cli.command import Context
from pinecall_runtime.enums import Role
from pinecall_runtime.kit.text import a_mapping

# Where the CLI keeps this machine's sign-in (`PINECALL_HOME` moves it): setup signs the machine in
# to this runtime there, as `pinecall login` would, in the CLI's own file and format
# (cli/src/project/session.ts): one entry per gateway, its key and its org, and the last one.
CLI_HOME_VARIABLE = "PINECALL_HOME"
CLI_SESSION_FILE = "session.json"
# What setup wrote before the sign-in was the CLI's one way in: taken away when found.
CLI_OLD_FILE = "local.json"
DEV_KEY = "PINECALL_DEV_KEY"
# Whose key it is: the console's person, so what `pinecall start` holds is the copy their console shows.
DEV_KEY_OF = "PINECALL_DEV_KEY_OF"
DEV_KEY_LABEL = "this machine (pinecall-runtime setup)"

# Where nobody is asked: an address that reads as this machine's.
NOBODY_ASKED = "admin@pinecall.local"
CHANGES_IT = "`pinecall-runtime orgs password default {email}` changes it"
# Nobody at a terminal and no line of stdin: no password is made up. The CLI is signed in anyway,
# and `pinecall console` opens the console from it; a password is set when somebody wants one.
NO_PASSWORD_YET = (
    "console    {email} has no password yet: `pinecall-runtime orgs password default {email}` sets one; "
    "`pinecall console` opens the console signed in"
)


async def the_person(
    runtime: Context, email: str | None, person: str | None, asking: bool, password_stdin: bool
) -> tuple[str, str]:
    """The console's admin, made or found, an operator, a password asked or read from stdin: the line said, their id."""
    address = email or (ask.email() if asking else NOBODY_ASKED)
    name = person or address.split("@", 1)[0]
    shortest = runtime.settings.min_password
    async with runtime.sessions.begin() as session:
        org = await orgs.get_org(session, DEFAULT_ORG)
        kept = await members.memberships_of(session, address.strip().lower())
        found = next((one for one in kept if one.org == org.id), None)
        if found is not None and found.password_hash is not None:
            return f"console    {found.email} keeps their password: {CHANGES_IT.format(email=found.email)}", found.id
        if found is None:
            invitee = members.Invitee(address, name, Role.admin)
            await members.invite(session, org.id, invitee, seats=None, vouched=True)
            found = await members.member_by_email(session, org.id, address)
        await members.set_operator(session, org.id, found.id, on=True)
        if not asking and not password_stdin:
            return NO_PASSWORD_YET.format(email=found.email), found.id
        password = orgs_cli.read_secret_line() if password_stdin else ask.password()
        await members.set_password(session, org.id, found.id, password, shortest)
    return (
        f"console    {found.email} signs in with the password typed: {CHANGES_IT.format(email=found.email)}",
        found.id,
    )


# A person's key, not a server's: in the sandbox a person's console shows that person's own copy of
# the agents, and a server's key holds the org's, which nobody's console showed (2026-10-17).
async def this_machines_key(runtime: Context, values: dict[str, str], env: Path, member: str) -> Path:
    """The console's person's key, drawn once into the env file, handed to the CLI every time."""
    if values.get(DEV_KEY_OF) != member or DEV_KEY not in values:
        async with runtime.sessions.begin() as session:
            found = await members.get_member(session, DEFAULT_ORG, member)
            _, values[DEV_KEY] = await keys.issue_person_key(session, found, label=DEV_KEY_LABEL)
        values[DEV_KEY_OF] = member
        kept = [
            line
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith((f"{DEV_KEY}=", f"{DEV_KEY_OF}="))
        ]
        env.write_text(
            "\n".join([*kept, f"{DEV_KEY}={values[DEV_KEY]}", f"{DEV_KEY_OF}={member}"]) + "\n", encoding="utf-8"
        )
    return hand_to_cli(values[DEV_KEY], cli_home(os.environ))


def cli_home(environ: Mapping[str, str]) -> Path:
    """Where the CLI keeps this machine's sign-in: `PINECALL_HOME`, else `~/.pinecall`."""
    named = environ.get(CLI_HOME_VARIABLE)
    return Path(named) if named else Path.home() / ".pinecall"


def hand_to_cli(secret: str, home: Path) -> Path:
    """This machine signed in to this runtime, in the CLI's session file, owner-only; its other gateways kept."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = home / CLI_SESSION_FILE
    gateways = dict(_gateways_in(path))
    kept = gateways.get(local.GATEWAY_URL)
    # A new sign-in: the keys minted from an earlier one go, the phone it calls from stays.
    entry: dict[str, object] = {"key": secret, "org": DEFAULT_ORG}
    if a_mapping(kept) and "calling" in kept:
        entry["calling"] = kept["calling"]
    gateways[local.GATEWAY_URL] = entry
    if not path.exists():
        path.touch(mode=0o600)
    path.write_text(json.dumps({"gateways": gateways, "last": local.GATEWAY_URL}, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    (home / CLI_OLD_FILE).unlink(missing_ok=True)
    return path


# The gateways the CLI's session already holds; none from a file that is not there or not its shape.
def _gateways_in(path: Path) -> Mapping[str, object]:
    try:
        read: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    gateways = read.get("gateways") if a_mapping(read) else None
    return gateways if a_mapping(gateways) else {}
