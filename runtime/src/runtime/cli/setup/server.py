"""`setup --domain`: this machine's runtime as a server — its name checked, Caddy, LiveKit facing out, kept up."""

import json
import secrets
import socket
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from livekit import api
from livekit.protocol.room import ListRoomsRequest

from runtime.cli.setup.compose import Compose
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
    phone = {"PINECALL_SIP_DOMAIN": server.name if server.phone else None}
    return {"PINECALL_DOMAIN": server.name, "PINECALL_GATEWAY_LISTEN": None, IMAGE: server.image, **livekit, **phone}


def bring_up(
    where: Path,
    server: Server,
    values: dict[str, str],
    wheel: Path | None,
    *,
    build: bool = True,
    again: Sequence[str] = (),
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
    services = ["postgres", "redis", "caddy", "gateway", *RUNTIME_BESIDE_THE_GATEWAY]
    services += [*(["livekit-server"] if server.livekit is None else []), *(["sip-server"] if server.phone else [])]
    services += ["postgres-backup"] if values.get(BACKUPS) else []
    up = ("--progress", "quiet", "up", "-d", "--wait", "--remove-orphans", *services)
    running = Compose(files, profiles, environment)
    running.run(*up, failed=UP_FAILED)
    # Compose starts a service again when what it was made with changed, and a file it only mounts is
    # not that. Caddy reads its own again with no connection dropped (the pages' name, a site of the
    # operator's); LiveKit and SIP read theirs once, so one whose config changed is started again.
    running.run("exec", "-T", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile", failed=UP_FAILED)
    if stale := [service for service in again if service in services]:
        running.run("--progress", "quiet", "restart", *stale, failed=UP_FAILED)


# Every profile of the server's compose file, so each service it names exists for compose.
EVERY_PROFILE = ("server", "server-livekit", "server-phone", "server-backups")
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
    serving = from_the_env(values)
    environment = {**values, **image_of(None, serving.image if serving else None)}
    return Compose(compose_files(where), profiles, environment)


def compose_files(where: Path) -> tuple[Path, ...]:
    """The services' compose file, and the server's laid over it where this machine is one."""
    server = where / "server.yaml"
    return (where / "compose.yaml", *([server] if server.is_file() else []))


def image_of(wheel: Path | None, image: str | None = None) -> dict[str, str]:
    """The image the runtime's services run, a registry's or the one built here, and what a build installs."""
    release = version("pinecall-runtime")
    spec = f"/wheels/{wheel.name}[voice]" if wheel is not None else f"pinecall-runtime[voice]=={release}"
    return {IMAGE: image or f"pinecall-runtime:{release}", "PINECALL_RUNTIME_SPEC": spec}
