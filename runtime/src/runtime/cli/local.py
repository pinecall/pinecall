"""`local`: the runtime whole on one machine: the services in Docker, the schema, the gateway, a worker, a runner."""

from pathlib import Path
from typing import Annotated

import typer

from runtime.accounts.models import BOX_ORG
from runtime.cli import orgs
from runtime.cli.command import OK, Context, context_of, verb
from runtime.cli.setup import children, compose, server
from runtime.cli.setup.database import prepare_database
from runtime.cli.setup.env_file import EnvFile
from runtime.cli.setup.files import DEFAULT_DIR, GATEWAY_URL, write_shipped
from runtime.enums import Role

app = typer.Typer(help="the runtime whole on this machine, for developing an agent", no_args_is_help=True)

UP = "local · Postgres :55433 · Redis :56380 · LiveKit :7880 · settings in {env}\nconsole   {gateway}/sandbox/"
FIRST = "  a runtime nobody set up yet: `pinecall-runtime setup` makes its admin and signs this machine in"
SERVING = "{name}: up, kept up by Docker across reboots · logs: pinecall-runtime local logs"
# Every profile the two compose files name, so `down` stops a server's services too.
ALL_PROFILES = ("phone", "server", "server-livekit", "server-phone")
DOWN = "local: the services stopped; the database and {env} are kept"
WIPED = "local: the services stopped and the database deleted; {env} is kept, its keys drawn again on the next up"

Dir = Annotated[Path, typer.Option("--dir", help="Where this machine keeps its local runtime.")]


# `local [--dir <path>] <verb>`: the directory stands before the verb, as the page says.
@app.callback()
def local_group(ctx: typer.Context, where: Dir = DEFAULT_DIR) -> None:
    """The runtime whole on this machine, for developing an agent."""
    ctx.meta["dir"] = where


def _where(ctx: typer.Context) -> Path:
    return Path(ctx.meta["dir"])


@app.command("up")
@verb
async def local_up(
    ctx: typer.Context,
    services_only: Annotated[bool, typer.Option("--services-only", help="The services and the schema alone.")] = False,
) -> int:
    """The services up, the schema at this release, the secrets drawn once, the gateway and a worker; a server's too."""
    context = context_of(ctx)
    where = _where(ctx)
    compose.docker_or_refuse()
    env = write_shipped(where)
    serving = server.from_the_env(env.read())
    compose.services_up(where, ("postgres", "redis") if serving else compose.SERVICES)
    history = await prepare_database(env, production_fleet=serving is not None)
    if serving is not None:
        server.bring_up(where, serving, env.read(), None, build=False)
        server.wait_for_https(serving.name)
        context.out.line(SERVING.format(name=f"https://{serving.name}"))
        return OK
    context.out.line(UP.format(env=env.path, gateway=GATEWAY_URL))
    if history.applied:
        context.out.line(FIRST)
    if services_only:
        return OK
    return children.run_children(context.out, env.read(), children.GATEWAY, children.WORKER, children.RUNNER)


@app.command("down")
@verb
async def local_down(
    ctx: typer.Context,
    volumes: Annotated[bool, typer.Option("--volumes", help="Delete the database too.")] = False,
) -> int:
    """Stop the services; the database's volume stays unless `--volumes`."""
    where = _where(ctx)
    compose.docker_or_refuse()
    compose.Compose(server.compose_files(where), ALL_PROFILES).follow("down", *(["-v"] if volumes else []))
    context_of(ctx).out.line((WIPED if volumes else DOWN).format(env=where / "env"))
    return OK


@app.command("logs")
@verb
async def local_logs(
    ctx: typer.Context,
    service: Annotated[str | None, typer.Argument(help="gateway, worker-sandbox, worker-production, caddy…")] = None,
) -> int:
    """Follow a server's logs, every service's or one's; a laptop's are in the terminal `setup` runs in."""
    where = _where(ctx)
    compose.docker_or_refuse()
    named = [service] if service else []
    return compose.Compose(server.compose_files(where), ALL_PROFILES).follow(
        "logs", "--follow", "--tail", "100", *named
    )


@app.command("init")
@verb
async def local_init(
    ctx: typer.Context,
    email: Annotated[str, typer.Option("--email")],
    person: Annotated[str, typer.Option("--person", help="The person's name.")],
    org: Annotated[str, typer.Option("--org", help="The org's slug.")] = BOX_ORG,
    name: Annotated[str | None, typer.Option("--name", help="What to call the org (default: the slug).")] = None,
    role: Annotated[Role, typer.Option("--role")] = orgs.THE_FIRST_ROLE,
) -> int:
    """The first org and person, on the local gateway: `init` on the local settings."""
    context = context_of(ctx)
    local = Context(EnvFile(_where(ctx) / "env").settings(), context.out)
    async with local.stack:
        return await orgs.initialize(local, org=org, name=name, email=email, person=person, role=role)


@app.command("env")
@verb
async def local_env(ctx: typer.Context) -> int:
    """Print the line a shell runs to use the local settings with any other verb."""
    context_of(ctx).out.secret(f"set -a; . {_where(ctx) / 'env'}; set +a")
    return OK
