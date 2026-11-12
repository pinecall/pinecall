"""Who `setup` makes: the console's admin of the box's own org, and this machine's key for the `pinecall` CLI."""

import os
from dataclasses import dataclass
from pathlib import Path

from runtime.accounts.models import BOX_ORG
from runtime.accounts.service import invitations, keys, members, orgs
from runtime.accounts.service.key_cache import KeyCache
from runtime.cli.command import Context
from runtime.cli.setup import ask
from runtime.cli.setup.cli_session import cli_home, hand_to_cli
from runtime.cli.setup.env_file import EnvFile
from runtime.cli.terminal import read_secret_line
from runtime.enums import Role
from runtime.exceptions import NotFound, ValidationError
from runtime.scoping import box_wide

DEV_KEY = "PINECALL_DEV_KEY"
# Whose key it is: the console's person, so what `pinecall start` holds is the copy their console shows.
DEV_KEY_OF = "PINECALL_DEV_KEY_OF"
DEV_KEY_LABEL = "this machine (pinecall-runtime setup)"
# Who the console's admin is, kept in the settings file, so a run after the first asks nothing.
ADMIN = "PINECALL_CONSOLE_ADMIN"
# Where nobody is asked: an address that reads as this machine's.
NOBODY_ASKED = "admin@pinecall.local"
# Nobody at a terminal and no line of stdin: no password is made up. The CLI is signed in anyway,
# and `pinecall console` opens the console from it; a password is set when somebody wants one.
NO_PASSWORD_YET = (
    "  console   {email} has no password yet: `pinecall-runtime orgs password default {email}` sets one; "
    "`pinecall console` opens the console signed in"
)


@dataclass(frozen=True)
class Answers:
    """Who signs in to the console, their name, and the password typed (None: none was asked for)."""

    email: str
    name: str
    password: str | None


def ask_person(
    email: str | None, person: str | None, values: dict[str, str], *, asking: bool, password_stdin: bool, server: bool
) -> Answers:
    """Asked before anything slow: who signs in and their password; nothing on a run after the first."""
    kept = values.get(ADMIN)
    if kept and not email and not password_stdin:
        return Answers(kept, person or kept.split("@", 1)[0], None)
    if password_stdin:
        address = email or kept or NOBODY_ASKED
        return Answers(address, person or address.split("@", 1)[0], read_secret_line())
    if not asking:
        if server:
            raise ValidationError(
                "a server's console needs a password: --password-stdin with --yes, or answer when asked"
            )
        address = email or NOBODY_ASKED
        return Answers(address, person or address.split("@", 1)[0], None)
    address = email or ask.email()
    return Answers(address, person or address.split("@", 1)[0], ask.password())


async def make_the_person(runtime: Context, answers: Answers, env: EnvFile) -> tuple[str | None, str]:
    """The console's admin, made or found, an operator, the password set: a line to say, if any, and their id."""
    handles = await runtime.handles()
    cache = KeyCache(handles.sessions, handles.signal)
    async with handles.sessions.begin() as session:
        with box_wide():
            org = await orgs.get_org(session, BOX_ORG)
            try:
                found = await members.get_member_by_email(session, org.id, answers.email)
            except NotFound:
                invitee = invitations.Invitee(answers.email, answers.name, Role.admin)
                found = (
                    await invitations.invite(session, org.id, invitee, vouched=True, held_to_seats=False)
                ).membership
            await members.set_operator(session, cache, found, on=True)
            none_yet = found.person.password_hash is None and answers.password is None
            if answers.password is not None:
                await members.set_password(session, found, answers.password, runtime.settings.min_password)
    env.set(**{ADMIN: found.email})
    return (NO_PASSWORD_YET.format(email=found.email) if none_yet else None), found.id


# A person's key, not a server's: in the sandbox a person's console shows that person's own copy of
# the agents, and a server's key holds the org's, which nobody's console showed (2026-10-17).
async def give_this_machine_a_key(runtime: Context, env: EnvFile, member: str) -> Path:
    """The console's person's key, drawn once into the settings file, handed to the CLI every time."""
    values = env.read()
    if values.get(DEV_KEY_OF) != member or DEV_KEY not in values:
        async with runtime.sessions.begin() as session:
            with box_wide():
                org = await orgs.get_org(session, BOX_ORG)
                found = await members.get_member(session, org.id, member)
                issued = await keys.issue_person_key(session, found.member, label=DEV_KEY_LABEL)
        values = env.set(**{DEV_KEY: issued.key, DEV_KEY_OF: member})
    return hand_to_cli(values[DEV_KEY], cli_home(os.environ))
