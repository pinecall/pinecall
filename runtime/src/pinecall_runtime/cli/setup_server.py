"""`setup --domain`: this machine's runtime as a server — its name checked, Caddy, LiveKit facing out, kept up."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from shutil import copyfile

from livekit import api
from livekit.protocol.room import ListRoomsRequest

from pinecall_runtime.exceptions import ConfigurationError, UpstreamError, ValidationError

# Where the machine's own public address is read, to say whether the name points here.
PUBLIC_ADDRESS = "https://checkip.amazonaws.com"
# How long the name is waited for over https: Caddy asks Let's Encrypt on its first start.
HTTPS_WITHIN_S = 120.0
LIVEKIT_KEY = "pinecall"
# `--livekit here`: the LiveKit setup starts again, after one of the operator's own.
HERE = "here"
FILES = ("server.yaml", "runtime/Dockerfile")

NOT_LINUX = "a server runs on Linux, which shares the host's network with Docker: on this machine, `setup` alone"
NOT_HERE = (
    "{name} points at {found}, and this machine is {here}: give {name} an A record to {here}, then run this again"
)
NOWHERE = "{name} resolves to no address: give it an A record to this machine's address, then run this again"
NO_PASSWORD = "a server's console needs a password: --password-stdin with --yes, or answer when asked"
LIVEKIT_REFUSED = "LiveKit at {url} refused that key and secret: {why}"
LIVEKIT_ON_A_LAPTOP = (
    "LiveKit must reach this runtime, and a laptop has no public address.\n"
    "    Run it on a server: pinecall-runtime setup --domain <name> --livekit <url>"
)
PHONE_ON_THEIR_LIVEKIT = (
    "--phone runs LiveKit's SIP beside the LiveKit setup starts; with your own LiveKit, phone calls go "
    "through that LiveKit's SIP"
)
NOT_ANSWERING = (
    "https://{name} did not answer within {seconds:.0f} s: open :80 and :443 to this machine "
    "(Let's Encrypt proves the name on :80), then `pinecall-runtime local up`"
)
BUILD_FAILED = "the runtime's image did not build:\n{output}"
UP_FAILED = "docker compose could not bring the server up:\n{output}"

CADDYFILE = """{name} {{
{livekit}	reverse_proxy 127.0.0.1:8080
}}
"""
# The browser's LiveKit is reached under the name: /rtc is LiveKit's signal path.
LIVEKIT_ROUTE = "\t@livekit path /rtc /rtc/*\n\treverse_proxy @livekit 127.0.0.1:7880\n"

LIVEKIT_CONFIG = """# LiveKit as a server: its media on the machine's public address, the pair drawn for this machine,
# its events to the gateway on loopback (one LiveKit serves both environments here).
port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: true
redis:
  address: 127.0.0.1:56380
keys:
  {key}: {secret}
webhook:
  api_key: {key}
  urls:
    - http://127.0.0.1:8080/v1/livekit/webhook
logging:
  level: info
"""

SIP_CONFIG = """# LiveKit's SIP as a server: calls to this machine's :5060, their audio on twenty RTP ports.
api_key: {key}
api_secret: {secret}
ws_url: ws://127.0.0.1:7880
redis:
  address: 127.0.0.1:56380
sip_port: 5060
rtp_port: 10000-10019
use_external_ip: true
logging:
  level: info
"""


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


def linux_or_refuse() -> None:
    """A server form runs on Linux alone."""
    if sys.platform != "linux":
        raise ConfigurationError(NOT_LINUX)


def check_name(name: str, *, read_address: bool = True) -> str:
    """The line that says the name points at this machine; refused when it points elsewhere or nowhere."""
    try:
        found = sorted({str(info[4][0]) for info in socket.getaddrinfo(name, 443, socket.AF_INET)})
    except socket.gaierror:
        raise ValidationError(NOWHERE.format(name=name)) from None
    here = this_machines_address() if read_address else None
    if here is None:
        return f"  name      {name} → {', '.join(found)} — this machine's address could not be read: be sure it is here"
    if here not in found:
        raise ValidationError(NOT_HERE.format(name=name, found=", ".join(found), here=here))
    return f"  name      {name} → {here} — this machine ✓"


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
        raise ValidationError(LIVEKIT_REFUSED.format(url=theirs.url, why=refused)) from refused
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
    return {"PINECALL_DOMAIN": server.name, "PINECALL_GATEWAY_LISTEN": None, **livekit, **phone}


def write_files(where: Path, server: Server, values: dict[str, str], wheel: Path | None) -> None:
    """The server's compose, its image's Dockerfile and wheel, the Caddyfile, LiveKit's and SIP's configs."""
    shipped = shipped_files()
    for name in FILES:
        target = where / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(shipped.joinpath("local", name).read_text(encoding="utf-8"), encoding="utf-8")
    wheels = where / "runtime" / "wheels"
    wheels.mkdir(exist_ok=True)
    for old in wheels.iterdir():
        old.unlink()
    if wheel is not None:
        copyfile(wheel, wheels / wheel.name)
    route = LIVEKIT_ROUTE if server.livekit is None else ""
    (where / "Caddyfile").write_text(CADDYFILE.format(name=server.name, livekit=route), encoding="utf-8")
    pair = {"key": values["LIVEKIT_API_KEY"], "secret": values["LIVEKIT_API_SECRET"]}
    for name, text in (("livekit.server.yaml", LIVEKIT_CONFIG), ("sip.server.yaml", SIP_CONFIG)):
        target = where / name
        target.touch(mode=0o600)
        target.write_text(text.format(**pair), encoding="utf-8")
        target.chmod(0o600)


def bring_up(where: Path, server: Server, values: dict[str, str], wheel: Path | None, *, build: bool = True) -> None:
    """The runtime's image built and every service up, kept up by Docker across reboots."""
    compose = compose_of(where)
    environment = {**values, **image_of(wheel)}
    # The laptop's LiveKit and SIP publish what the server's take on the host's network; a service
    # this server no longer runs (its LiveKit for theirs, SIP turned off) is stopped, not left behind.
    unused = [
        "livekit",
        "sip",
        *(["livekit-server"] if server.livekit else []),
        *([] if server.phone else ["sip-server"]),
    ]
    _run([*compose, "rm", "--stop", "--force", *unused], environment, UP_FAILED)
    if build:
        _run([*compose, "--profile", "server", "build", "gateway"], environment, BUILD_FAILED)
    profiles = ["--profile", "server"]
    if server.livekit is None:
        profiles += ["--profile", "server-livekit"]
    if server.phone:
        profiles += ["--profile", "server-phone"]
    services = ["postgres", "redis", "caddy", "gateway", "worker-sandbox", "worker-production"]
    services += [*(["livekit-server"] if server.livekit is None else []), *(["sip-server"] if server.phone else [])]
    _run([*compose, *profiles, "up", "-d", "--wait", "--remove-orphans", *services], environment, UP_FAILED)


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
                raise UpstreamError(NOT_ANSWERING.format(name=name, seconds=within_s)) from None
            time.sleep(3)


def shipped_files() -> Traversable:
    """What the package ships for Docker: the `cli` package's `local/` (`cli.local` is a module to importlib)."""
    return files("pinecall_runtime.cli")


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
    return Server(name, theirs, phone=bool(values.get("PINECALL_SIP_DOMAIN")))


def compose_of(where: Path) -> list[str]:
    """`docker compose` on the services' file and the server's laid over it."""
    # Quiet: what a failure says is the error, not the progress of every layer pulled.
    return [
        "docker",
        "compose",
        "--progress",
        "quiet",
        "-f",
        str(where / "compose.yaml"),
        "-f",
        str(where / "server.yaml"),
    ]


def image_of(wheel: Path | None) -> dict[str, str]:
    """The image's tag and what it installs: this release from PyPI, or the wheel given."""
    release = version("pinecall-runtime")
    spec = f"/wheels/{wheel.name}[voice]" if wheel is not None else f"pinecall-runtime[voice]=={release}"
    return {"PINECALL_RUNTIME_VERSION": release, "PINECALL_RUNTIME_SPEC": spec}


def _run(command: list[str], environment: dict[str, str], failed: str) -> None:
    done = subprocess.run(command, capture_output=True, text=True, check=False, env={**os.environ, **environment})
    if done.returncode != 0:
        raise UpstreamError(failed.format(output=(done.stderr or done.stdout).strip()[-2000:]))
