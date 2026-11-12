"""docker compose as the installer runs it: the files a server's services are laid over."""

from pathlib import Path

from runtime.cli.setup.files import write_shipped
from runtime.cli.setup.server import compose_files


def test_a_servers_compose_is_laid_over_the_services(tmp_path: Path) -> None:
    """`down` and `logs` reach a server's services too, once server.yaml is there."""
    write_shipped(tmp_path)
    assert compose_files(tmp_path) == (tmp_path / "compose.yaml",)
    (tmp_path / "server.yaml").write_text("services: {}\n")
    assert compose_files(tmp_path) == (tmp_path / "compose.yaml", tmp_path / "server.yaml")
