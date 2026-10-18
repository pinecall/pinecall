"""`setup`'s person: this machine signed in to its own runtime in the CLI's session file, and the CLI's home."""

import json
import stat
from pathlib import Path

from pinecall_runtime.cli import local, setup_person


def test_this_machine_is_signed_in_to_the_runtime_as_the_cli_keeps_a_sign_in(tmp_path: Path) -> None:
    """`~/.pinecall/session.json`, owner-only: the local gateway's key and org, the last one signed in to."""
    home = tmp_path / ".pinecall"
    signed = setup_person.hand_to_cli("pc_live_secret", home)
    assert signed == home / "session.json"
    assert stat.S_IMODE(signed.stat().st_mode) == 0o600
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    assert json.loads(signed.read_text(encoding="utf-8")) == {
        "gateways": {local.GATEWAY_URL: {"key": "pc_live_secret", "org": "default"}},
        "last": local.GATEWAY_URL,
    }


def test_another_gateways_sign_in_and_the_phone_are_kept_and_the_old_file_goes(tmp_path: Path) -> None:
    """A cloud sign-in stays; the local entry's minted keys go with its old key, its phone stays; local.json is gone."""
    home = tmp_path / ".pinecall"
    home.mkdir()
    (home / "local.json").write_text("{}", encoding="utf-8")
    earlier = {
        "gateways": {
            "https://cloud.pinecall.io": {"key": "pc_live_cloud", "org": "clinica"},
            local.GATEWAY_URL: {"key": "pc_live_old", "org": "default", "orgs": {"acme": "k"}, "calling": "+5989"},
        },
        "last": "https://cloud.pinecall.io",
    }
    (home / "session.json").write_text(json.dumps(earlier), encoding="utf-8")
    setup_person.hand_to_cli("pc_live_newer", home)
    read = json.loads((home / "session.json").read_text(encoding="utf-8"))
    assert read["gateways"]["https://cloud.pinecall.io"] == {"key": "pc_live_cloud", "org": "clinica"}
    assert read["gateways"][local.GATEWAY_URL] == {"key": "pc_live_newer", "org": "default", "calling": "+5989"}
    assert read["last"] == local.GATEWAY_URL
    assert not (home / "local.json").exists()


def test_the_clis_home_follows_its_own_variable(tmp_path: Path) -> None:
    """`PINECALL_HOME` moves the file as it moves the CLI's sign-in; `~/.pinecall` otherwise."""
    assert setup_person.cli_home({"PINECALL_HOME": str(tmp_path)}) == tmp_path
    assert setup_person.cli_home({}) == Path.home() / ".pinecall"


def test_nobody_at_a_terminal_gets_no_made_up_password() -> None:
    """Under `--yes` the admin has no password: the line says what sets one and that the CLI opens the console."""
    said = setup_person.NO_PASSWORD_YET.format(email="admin@pinecall.local")
    assert "has no password yet" in said
    assert "orgs password default admin@pinecall.local" in said
    assert "pinecall console" in said
