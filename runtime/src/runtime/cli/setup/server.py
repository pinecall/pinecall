"""`setup --domain`: this machine's runtime as a server — its name checked, Caddy, LiveKit facing out, kept up."""

import json
import secrets
import socket
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from livekit import api
from livekit.protocol.room import ListRoomsRequest

from runtime.cli.setup.compose import Compose, compose_files
from runtime.exceptions import ConfigurationError, UpstreamError, ValidationError

# Where the machine's own public address is read, to say whether the name points here.
PUBLIC_ADDRESS = "https://checkip.amazonaws.com"
# How long the name is waited for over https: Caddy asks Let's Encrypt on its first start.
HTTPS_WITHIN_S = 120.0
LIVEKIT_KEY = "pinecall"
# `--livekit here`: the LiveKit setup starts again, after one of the operator's own; `--image here`:
# the image built on this machine again, after one from a registry.
HERE = "here"
# The env file's name for the registry's image a server runs; it stays as `setup --image` wrote it.
IMAGE = "PINECALL_RUNTIME_IMAGE"
# Where the database's backups go (s3://… or gs://…): named, the nightly base backups run beside Postgres.
BACKUPS = "PINECALL_BACKUP_URL"
# What a server's gateways connect to Postgres as: a role that reads and writes every table's rows and
# changes none (database.py makes it, the migrations grant it), and the URL with its password.
APP_ROLE = "pinecall_app"
APP_URL = "PINECALL_DB_APP_URL"
# Redis's password on a server, and the URL the gateways reach it at; a laptop's asks none.
REDIS_PASSWORD = "PINECALL_REDIS_PASSWORD"
REDIS_AT = "127.0.0.1:56380/0"
BUILD_FAILED = "the runtime's image did not build:\n{output}"
PULL_FAILED = "the runtime's image could not be pulled:\n{output}"
UP_FAILED = "docker compose could not bring the server up:\n{output}"


@dataclass(frozen=True)
class TheirLiveKit:
    """A LiveKit of the operator's own: where it is, and the pair that signs for it."""

    url: str
    key: str
    secret: str


@dataclass(frozen=True)
class Server:
    """What this machine serves as: its name, whose LiveKit, whether it takes phone calls."""

    name: str
    livekit: TheirLiveKit | None = None
    phone: bool = False
    # The image every process of the runtime runs, from a registry; None builds it on this machine.
    image: str | None = None


def linux_or_refuse() -> None:
    """A server form runs on Linux alone."""
    if sys.platform != "linux":
        raise ConfigurationError(
            "a server runs on Linux, which shares the host's network with Docker: on this machine, `setup` alone"
        )


# Resolves a name to its IPv4 addresses, as the box's DNS answers; a test hands in its own.
type Resolve = Callable[[str], list[str]]
# The address the internet sees this machine at, or None; a test hands in its own.
type Here = Callable[[], str | None]


def resolve_ipv4(name: str) -> list[str]:
    """Every IPv4 address the name resolves to now; socket.gaierror when none."""
    return sorted({str(info[4][0]) for info in socket.getaddrinfo(name, 443, socket.AF_INET)})


def check_name(name: str, *, resolve: Resolve = resolve_ipv4, here: Here | None = None) -> str:
    """The line that says the name points at this machine; refused when it points elsewhere or nowhere."""
    try:
        found = resolve(name)
    except socket.gaierror:
        raise ValidationError(
            f"{name} resolves to no address: give it an A record to this machine's address, then run this again"
        ) from None
    address = (here or this_machines_address)()
    if address is None:
        return f"  name      {name} → {', '.join(found)} — this machine's address could not be read: be sure it is here"
    if address not in found:
        raise ValidationError(
            f"{name} points at {', '.join(found)}, and this machine is {address}: give {name} an A record to "
            f"{address}, then run this again"
        )
    return f"  name      {name} → {address} — this machine ✓"


def this_machines_address() -> str | None:
    """The address the internet sees this machine at, or None when it cannot be asked."""
    try:
        with urllib.request.urlopen(PUBLIC_ADDRESS, timeout=5) as answer:
            read: bytes = answer.read()
    except OSError:
        return None
    return read.decode().strip() or None


async def check_their_livekit(theirs: TheirLiveKit) -> None:
    """The operator's LiveKit asked one thing on their pair, or refused in its words."""
    server = api.LiveKitAPI(theirs.url, theirs.key, theirs.secret)
    try:
        await server.room.list_rooms(ListRoomsRequest())
    except (api.TwirpError, OSError) as refused:
        raise ValidationError(f"LiveKit at {theirs.url} refused that key and secret: {refused}") from refused
    finally:
        await server.aclose()


def settings_of(server: Server, values: dict[str, str]) -> dict[str, str | None]:
    """What the env file says on a server: the name, whose LiveKit and its pair, the gateway on loopback."""
    if server.livekit is not None:
        livekit: dict[str, str | None] = {
            "LIVEKIT_URL": server.livekit.url,
            "LIVEKIT_API_KEY": server.livekit.key,
            "LIVEKIT_API_SECRET": server.livekit.secret,
            "LIVEKIT_PUBLIC_URL": server.livekit.url,
        }
    else:
        drawn = values.get("LIVEKIT_API_KEY") == LIVEKIT_KEY
        livekit = {
            "LIVEKIT_URL": "ws://127.0.0.1:7880",
            "LIVEKIT_API_KEY": LIVEKIT_KEY,
            # Drawn once for this machine: a laptop's development pair never signs for a server.
            "LIVEKIT_API_SECRET": values["LIVEKIT_API_SECRET"] if drawn else secrets.token_urlsafe(32),
            "LIVEKIT_PUBLIC_URL": None,
        }
    # LiveKit and the gateway share the host's network: the gateway stays on loopback, Caddy is the door.
    # The name carriers send calls to is the server's own unless the env file says another: a
    # runtime moved here keeps the one its carriers' trunks already name.
    phone = {"PINECALL_SIP_DOMAIN": (values.get("PINECALL_SIP_DOMAIN") or server.name) if server.phone else None}
    named = {"PINECALL_DOMAIN": server.name, "PINECALL_GATEWAY_LISTEN": None, IMAGE: server.image}
    return {**named, **livekit, **phone, **passwords_of(values)}


# Drawn once and kept: the gateways' role and its password, Redis's. Each is drawn before anything is
# brought up, so the services are first started with them; the role itself is made by database.py.
def passwords_of(values: dict[str, str]) -> dict[str, str | None]:
    """Redis's password and its URL, the app role's name and URL: the env file's own, else drawn."""
    redis = values.get(REDIS_PASSWORD) or secrets.token_hex(24)
    app = values.get(APP_URL) or f"postgresql://{APP_ROLE}:{secrets.token_hex(24)}@127.0.0.1:55433/pinecall"
    return {
        REDIS_PASSWORD: redis,
        "PINECALL_REDIS_URL": f"redis://:{redis}@{REDIS_AT}",
        "PINECALL_DB_APP_ROLE": APP_ROLE,
        APP_URL: app,
    }


def bring_up(
    where: Path,
    server: Server,
    values: dict[str, str],
    wheel: Path | None,
    *,
    build: bool = True,
) -> None:
    """The runtime's image built or pulled and every service up, kept up by Docker across reboots."""
    files = compose_files(where)
    environment = {**values, **image_of(wheel, server.image)}
    # Every profile of the server, so each service named exists for compose: `sip-server` depends on
    # `livekit-server`, and with its profile off compose refused the removal as "no such service".
    every = Compose(files, EVERY_PROFILE, environment)
    # The laptop's LiveKit and SIP publish what the server's take on the host's network; a service
    # this server no longer runs (its LiveKit for theirs, SIP turned off) is stopped, not left behind.
    unused = [
        "livekit",
        "sip",
        *(["livekit-server"] if server.livekit else []),
        *([] if server.phone else ["sip-server"]),
        *([] if values.get(BACKUPS) else ["postgres-backup"]),
    ]
    every.run("--progress", "quiet", "rm", "--stop", "--force", *unused, failed=UP_FAILED)
    if build and server.image is None:
        Compose(files, ("server",), environment).run("--progress", "quiet", "build", "gateway", failed=BUILD_FAILED)
    elif build:
        # A registry's image is never built here: pulled once by the gateway's name, run by every service.
        Compose(files, ("server",), environment).run("--progress", "quiet", "pull", "gateway", failed=PULL_FAILED)
    profiles = (
        "server",
        *(["server-livekit"] if server.livekit is None else []),
        *(["server-phone"] if server.phone else []),
        *(["server-backups"] if values.get(BACKUPS) else []),
    )
    services = ["postgres", "redis", "caddy", *GATEWAYS, *RUNTIME_BESIDE_THE_GATEWAY]
    services += [*(["livekit-server"] if server.livekit is None else []), *(["sip-server"] if server.phone else [])]
    services += ["postgres-backup"] if values.get(BACKUPS) else []
    up = ("--progress", "quiet", "up", "-d", "--wait")
    running = Compose(files, profiles, environment)
    # What the processes write made theirs before any of them starts (server.yaml, `own`).
    running.run("--progress", "quiet", "run", "--rm", "--no-deps", "own", failed=UP_FAILED)
    # In an order that leaves the name answering through an update. Caddy first: compose starts a
    # service again when what it was made with changed, and a file it only mounts is not that, so
    # Caddy is told to read its own again, with no connection dropped (the two gateways, the pages'
    # name, a site of the operator's). Then one gateway, waited for until it answers while the other
    # serves, then the other. Then everything else: a worker told to stop ends when its calls do.
    running.run(*up, "--no-deps", "caddy", failed=UP_FAILED)
    running.run("exec", "-T", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile", failed=UP_FAILED)
    for gateway in GATEWAYS:
        running.run(*up, "--no-deps", gateway, failed=UP_FAILED)
    # LiveKit's and SIP's configs are said in the compose file from the env file's values: one that
    # changed is a service compose starts again by itself.
    running.run(*up, "--remove-orphans", *services, failed=UP_FAILED)


# Every profile of the server's compose file, so each service it names exists for compose.
EVERY_PROFILE = ("server", "server-livekit", "server-phone", "server-backups")
# A server's two gateways, in the order an update starts them again.
GATEWAYS = ("gateway", "gateway-b")
# What runs on the runtime's image beside the gateway: each environment's worker and overflow, and the night.
RUNTIME_BESIDE_THE_GATEWAY = (
    "worker-sandbox",
    "worker-production",
    "overflow-sandbox",
    "overflow-production",
    "retention",
)


def wait_for_https(name: str, within_s: float = HTTPS_WITHIN_S) -> None:
    """Wait until the name answers over https with a certificate, or say what to open."""
    deadline = time.monotonic() + within_s
    while True:
        try:
            with urllib.request.urlopen(f"https://{name}/.well-known/pinecall", timeout=5) as answer:
                json.loads(answer.read() or b"{}")
                return
        except (OSError, ValueError):
            if time.monotonic() > deadline:
                raise UpstreamError(
                    f"https://{name} did not answer within {within_s:.0f} s: open :80 and :443 to this machine "
                    "(Let's Encrypt proves the name on :80), then `pinecall-runtime local up`"
                ) from None
            time.sleep(3)


def from_the_env(values: dict[str, str]) -> Server | None:
    """The server an env file describes, or None for a laptop's: its name, their LiveKit, its phone."""
    name = values.get("PINECALL_DOMAIN")
    if not name:
        return None
    url = values.get("LIVEKIT_URL", "")
    theirs = (
        None
        if url.startswith("ws://127.0.0.1")
        else TheirLiveKit(url, values["LIVEKIT_API_KEY"], values["LIVEKIT_API_SECRET"])
    )
    return Server(name, theirs, phone=bool(values.get("PINECALL_SIP_DOMAIN")), image=values.get(IMAGE) or None)


# Compose reads both files whole whatever it is asked, and a service whose image is no name is no
# project to it: every verb on a server's services, `logs` and `down` too, is given what the files
# read, the env file's values and the image.
def every_service(where: Path, values: dict[str, str], profiles: tuple[str, ...] = EVERY_PROFILE) -> Compose:
    """docker compose on this machine's files with every profile on: what stops, follows or removes any service."""
    return Compose(compose_files(where), profiles, environment_of(values))


def environment_of(values: dict[str, str], wheel: Path | None = None) -> dict[str, str]:
    """What compose reads the files with: the env file's values, and the image the runtime's services run."""
    serving = from_the_env(values)
    return {**values, **image_of(wheel, serving.image if serving else None)}


def image_of(wheel: Path | None, image: str | None = None) -> dict[str, str]:
    """The image the runtime's services run, a registry's or the one built here, and what a build installs."""
    release = version("pinecall-runtime")
    spec = f"/wheels/{wheel.name}[voice]" if wheel is not None else f"pinecall-runtime[voice]=={release}"
    return {IMAGE: image or f"pinecall-runtime:{release}", "PINECALL_RUNTIME_SPEC": spec}
