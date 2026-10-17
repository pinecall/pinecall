"""`setup`: the key handed to the CLI, and the providers row it seeds for local models or for vendor keys."""

import json
import stat
from pathlib import Path

from pinecall_runtime.cli import local, setup


def test_the_key_is_handed_to_the_cli_in_a_file_of_its_own(tmp_path: Path) -> None:
    """`~/.pinecall/local.json`, owner-only, naming the local gateway, the key and the org."""
    home = tmp_path / ".pinecall"
    handed = setup.hand_to_cli("pc_test_secret", home)
    assert handed == home / "local.json"
    assert stat.S_IMODE(handed.stat().st_mode) == 0o600
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    read = json.loads(handed.read_text(encoding="utf-8"))
    assert read == {
        "url": local.GATEWAY_URL,
        "key": "pc_test_secret",
        "org": "default",
        "written_by": "pinecall-runtime setup",
    }
    # Run again, a new key replaces the old one and the file stays owner-only.
    setup.hand_to_cli("pc_test_newer", home)
    assert json.loads(handed.read_text(encoding="utf-8"))["key"] == "pc_test_newer"
    assert stat.S_IMODE(handed.stat().st_mode) == 0o600


def test_the_clis_home_follows_its_own_variable(tmp_path: Path) -> None:
    """`PINECALL_HOME` moves the file as it moves the CLI's sign-in; `~/.pinecall` otherwise."""
    assert setup.cli_home({"PINECALL_HOME": str(tmp_path)}) == tmp_path
    assert setup.cli_home({}) == Path.home() / ".pinecall"
