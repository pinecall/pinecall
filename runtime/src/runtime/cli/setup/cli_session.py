"""This machine signed in to its own runtime, in the `pinecall` CLI's session file, as `pinecall login` keeps it."""

import json
from collections.abc import Mapping
from pathlib import Path

from runtime.accounts.models import BOX_ORG
from runtime.cli.setup.files import GATEWAY_URL
from runtime.kit.text import a_mapping

# Where the CLI keeps this machine's sign-in (`PINECALL_HOME` moves it): one entry per gateway, its key
# and its org, and the last one (cli/src/project/session.ts).
CLI_HOME_VARIABLE = "PINECALL_HOME"
CLI_SESSION_FILE = "session.json"
# What setup wrote before the sign-in was the CLI's one way in: taken away when found.
CLI_OLD_FILE = "local.json"


def cli_home(environ: Mapping[str, str]) -> Path:
    """Where the CLI keeps this machine's sign-in: `PINECALL_HOME`, else `~/.pinecall`."""
    named = environ.get(CLI_HOME_VARIABLE)
    return Path(named) if named else Path.home() / ".pinecall"


def hand_to_cli(secret: str, home: Path) -> Path:
    """This machine signed in to this runtime, in the CLI's session file, owner-only; its other gateways kept."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = home / CLI_SESSION_FILE
    gateways = dict(_gateways_in(path))
    kept = gateways.get(GATEWAY_URL)
    # A new sign-in: the keys minted from an earlier one go, the phone it calls from stays.
    entry: dict[str, object] = {"key": secret, "org": BOX_ORG}
    if a_mapping(kept) and "calling" in kept:
        entry["calling"] = kept["calling"]
    gateways[GATEWAY_URL] = entry
    if not path.exists():
        path.touch(mode=0o600)
    path.write_text(json.dumps({"gateways": gateways, "last": GATEWAY_URL}, indent=2) + "\n", encoding="utf-8")
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
