"""The installation's settings file: a name set, one added, one taken out, every other line kept."""

from pathlib import Path

from runtime.cli.setup.files import write_shipped


def test_set_replaces_adds_and_takes_out_keeping_the_rest(tmp_path: Path) -> None:
    """A server's settings land in the file: a name set, one added, one taken out, every secret kept."""
    env = write_shipped(tmp_path)
    vault = env.read()["PINECALL_VAULT_KEY"]
    values = env.set(LIVEKIT_URL="wss://x", PINECALL_DOMAIN="a.example", PINECALL_FLEET=None)
    assert values["LIVEKIT_URL"] == "wss://x" and values["PINECALL_DOMAIN"] == "a.example"
    assert "PINECALL_FLEET" not in values and values["PINECALL_VAULT_KEY"] == vault


def test_the_file_is_the_owners_alone(tmp_path: Path) -> None:
    assert write_shipped(tmp_path).path.stat().st_mode & 0o077 == 0
