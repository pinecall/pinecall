"""What one run of `setup` does, in order: the server, the choices and keys, the person, the services, the row."""

import logging
from dataclasses import dataclass
from pathlib import Path

from runtime.cli.command import OK, Context
from runtime.cli.output import Printer
from runtime.cli.setup import ask, children, compose, models, person, server
from runtime.cli.setup import keys as found_keys
from runtime.cli.setup.choices import Choices, choices_of
from runtime.cli.setup.database import prepare_database
from runtime.cli.setup.env_file import EnvFile
from runtime.cli.setup.files import GATEWAY_URL, write_shipped
from runtime.cli.terminal import read_secret_line
from runtime.exceptions import ValidationError

NEXT_HERE = """  ✓ ready   {gateway}/sandbox/
  ✓ this machine is signed in — no `pinecall login` needed

  Next, in another terminal:
    npm i -g pinecall
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in a third terminal: talk to it
"""
NEXT_SERVER = """  ✓ ready   https://{name}
  ✓ {email} runs this runtime and is admin of org default

  From your laptop:
    npm i -g pinecall
    pinecall login https://{name}
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in another terminal: talk to it

  More orgs: the console → Box → Organizations · logs: pinecall-runtime local logs
"""
WEBHOOK = """
  One step in your LiveKit → Settings → Webhooks, signed with {key}:
    https://{name}/v1/livekit/webhook
"""


@dataclass(frozen=True)
class Flags:
    """What a run of setup was asked, flag by flag, as the verb read them."""

    where: Path
    domain: str | None
    livekit: str | None
    phone: bool
    livekit_key: str | None
    livekit_secret_stdin: bool
    wheel: Path | None
    email: str | None
    person: str | None
    password_stdin: bool
    asking: bool
    models: str | None
    stt: str | None
    turn: str | None
    llm: str | None
    tts: str | None
    judge: str | None
    caller: str | None
    chat_only: bool
    services_only: bool


async def carry_out(flags: Flags, out: Printer) -> int:
    """One run of setup, what is done already skipped: the server, the services, the person, the row; then running."""
    env = EnvFile(flags.where / "env")
    first_run = not env.exists()
    before = env.read()
    wanted = await server_for(flags, before)
    out.line(f"\n  Pinecall runtime · {wanted.name if wanted else 'on this machine'}\n")
    if wanted is not None:
        server.linux_or_refuse()
        out.line(server.check_name(wanted.name))
        out.line("  https     certificate from Let's Encrypt, renews itself")
        if wanted.livekit is not None:
            out.line(f"  livekit   {wanted.livekit.url} ✓")
    # Decided before anything is brought up: the keys found, the open models, a key missing.
    choices = choices_of(
        flags.models, flags.stt, flags.turn, flags.llm, flags.tts, flags.judge, flags.caller, chat_only=flags.chat_only
    )
    card = models.a_card_for_docker() if choices else False
    keys = _keys(choices, asking=flags.asking, out=out, server=wanted is not None, card=card) if choices else {}
    answers = person.ask_person(
        flags.email, flags.person, before, asking=flags.asking, password_stdin=flags.password_stdin, server=bool(wanted)
    )
    if first_run:
        out.line("\n  starting  the first run downloads the services and the models: some minutes")
    env = write_shipped(flags.where)
    started = ("postgres", "redis") if flags.chat_only or wanted else compose.SERVICES
    compose.services_up(flags.where, started)
    if wanted is None:
        named = " · ".join(name for name, (_, service) in compose.PORTS.items() if service in started)
        out.line(f"  services  {named} — this machine only")
    else:
        env.set(**server.settings_of(wanted, env.read()))
    # The schema's revisions, one INFO line each, are the operator's to read in `migrate up`, not a setup's.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    await prepare_database(env, production_fleet=wanted is not None)
    runtime = Context(env.settings(), out)
    async with runtime.stack:
        said, member = await person.make_the_person(runtime, answers, env)
        if said:
            out.line(said)
        if wanted is None:
            await person.give_this_machine_a_key(runtime, env, member)
        if choices is not None:
            await models.models(runtime, flags.where, choices, keys, card=card)
    values = env.read()
    if wanted is not None:
        return _serve(flags.where, wanted, values, flags.wheel, answers.email, out)
    out.line("\n" + NEXT_HERE.format(gateway=GATEWAY_URL))
    if flags.services_only:
        return OK
    running = (
        (children.GATEWAY, children.RUNNER) if flags.chat_only else (children.GATEWAY, children.WORKER, children.RUNNER)
    )
    return children.run_children(out, values, *running)


async def server_for(flags: Flags, before: dict[str, str]) -> server.Server | None:
    """The server this run makes: the name given or already served, their LiveKit given or kept; None on a laptop."""
    kept = server.from_the_env(before)
    name = flags.domain or (kept.name if kept else None)
    if name is None:
        if flags.livekit is not None:
            raise ValidationError(
                "LiveKit must reach this runtime, and a laptop has no public address.\n    Run it on a server: "
                "pinecall-runtime setup --domain <name> --livekit <url>"
            )
        if flags.phone:
            raise ValidationError("--phone is a server's: --domain <name> --phone")
        return None
    theirs = kept.livekit if kept and flags.livekit is None else None
    if flags.livekit is not None and flags.livekit != server.HERE:
        if flags.livekit_key is None and not flags.asking:
            raise ValidationError("--livekit needs --livekit-key and --livekit-secret-stdin with --yes")
        typed_key = flags.livekit_key or ask.livekit_key()
        typed_secret = read_secret_line() if flags.livekit_secret_stdin else ask.livekit_secret()
        theirs = server.TheirLiveKit(flags.livekit, typed_key, typed_secret)
    with_phone = flags.phone or (kept.phone if kept else False)
    if theirs is not None and with_phone:
        raise ValidationError(
            "--phone runs LiveKit's SIP beside the LiveKit setup starts; with your own LiveKit, phone calls go "
            "through that LiveKit's SIP"
        )
    if theirs is not None:
        # Tried every run, a kept pair too: the ✓ setup prints says the pair works today.
        await server.check_their_livekit(theirs)
    return server.Server(name, theirs, phone=with_phone)


def _serve(
    where: Path, wanted: server.Server, values: dict[str, str], wheel: Path | None, email: str, out: Printer
) -> int:
    services = "Postgres · Redis" + (" · LiveKit" if wanted.livekit is None else " — LiveKit is yours")
    out.line(f"  services  {services}")
    if wanted.livekit is not None:
        out.line("  phone     through your LiveKit's own SIP")
    else:
        out.line("  phone     on: SIP on :5060" if wanted.phone else "  phone     off — `--phone` turns it on")
    server.write_files(where, wanted, values, wheel)
    server.bring_up(where, wanted, values, wheel)
    server.wait_for_https(wanted.name)
    out.line("\n" + NEXT_SERVER.format(name=wanted.name, email=email))
    if wanted.livekit is not None:
        out.line(WEBHOOK.format(key=wanted.livekit.key, name=wanted.name))
    return OK


# Every key found is loaded, so an agent may name any vendor of yours with nothing to add; a key
# the defaults need and found nowhere is asked for at a terminal, else refused.
def _keys(choices: Choices, *, asking: bool, out: Printer, server: bool, card: bool) -> dict[str, str]:
    loaded, places = found_keys.keys_found()
    out.line(found_keys.say_keys(loaded, places, server=server))
    out.line(found_keys.say_models(choices, card=card))
    keys, _ = found_keys.keys_for(choices, ask=ask.secret if asking else None)
    # A real key wins over the word the embedder's plugin is given when none is.
    return {**keys, **loaded}
