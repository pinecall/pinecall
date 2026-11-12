"""What the package ships for one machine's runtime, written where it keeps it, and the settings drawn once."""

import base64
import secrets
import sys
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from runtime.cli.setup.env_file import EnvFile

# Where one machine keeps its runtime: the compose files, the settings, the recordings.
DEFAULT_DIR = Path.home() / ".pinecall-runtime" / "local"
# What the package ships for Docker, written into that directory as they are here (`shipped/`).
SHIPPED = (
    "compose.yaml",
    "livekit.yaml",
    "sip.yaml",
    "postgres/Dockerfile",
    "postgres/extensions.sql",
    "models.yaml",
    "models.gpu.yaml",
    "providers.local.json",
    "prices.csv",
    "prices.LICENSE",
    "models.csv",
    "measured.csv",
)
GATEWAY_URL = "http://127.0.0.1:8080"
# The settings the gateway and the worker run on here: the services on loopback, a dev LiveKit pair, secrets drawn once.
SETTINGS = """DATABASE_URL=postgresql://pinecall:pinecall@127.0.0.1:55433/pinecall
PINECALL_REDIS_URL=redis://127.0.0.1:56380/0
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=a-laptop-only-livekit-secret-0123456789
PINECALL_GATEWAY_URL={gateway}
PINECALL_RECORDINGS={recordings}
PINECALL_FLEET=pinecall-sandbox
PINECALL_MAX_JOBS=4
PINECALL_WORKER_HTTP_PORT=8182
PINECALL_VAULT_KEY={vault}
PINECALL_OPS_KEY=pc_ops_{ops}
PINECALL_TOKEN_KEY={token}
{listen}"""
# On Linux, host.docker.internal is Docker's bridge, not loopback: LiveKit's webhooks need a gateway on every interface.
LISTEN_EVERYWHERE = "PINECALL_GATEWAY_LISTEN=0.0.0.0:8080\n" if sys.platform == "linux" else ""


def shipped(name: str) -> Traversable:
    """One file the package ships for a machine's runtime."""
    return files("runtime.cli.setup").joinpath("shipped", name)


def write_shipped(where: Path) -> EnvFile:
    """Write the files the package ships, changed or missing, and the settings once; the settings file."""
    for name in SHIPPED:
        target = where / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = shipped(name).read_text(encoding="utf-8")
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
    (where / "recordings").mkdir(exist_ok=True)
    env = EnvFile(where / "env")
    if not env.exists():
        env.create(
            SETTINGS.format(
                gateway=GATEWAY_URL,
                recordings=where / "recordings",
                vault=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                ops=secrets.token_hex(24),
                token=secrets.token_hex(32),
                listen=LISTEN_EVERYWHERE,
            )
        )
    return env
