"""The app's page on this machine: its files, its config, and the visitor's ticket passed on."""

import json
from pathlib import Path

from pinecall.serve._paged import NOT_BUILT, Paging, file_of, got, posted


def paging(folder: Path) -> Paging:
    return Paging(folder, "front-desk", "http://127.0.0.1:9", "pk_test", None, 0)


def test_a_path_that_names_no_file_is_the_page_itself_and_a_missing_file_is_said(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text("<p>page</p>", encoding="utf-8")
    (tmp_path / "app.js").write_text("go()", encoding="utf-8")
    assert file_of(tmp_path, "/agenda/lunes").body == b"<p>page</p>"
    shown = file_of(tmp_path, "/app.js")
    assert (shown.body, shown.kind) == (b"go()", "text/javascript")
    assert file_of(tmp_path, "/missing.css").status == 404
    assert file_of(tmp_path, "/../secret").status == 404


def test_a_page_not_built_yet_says_so(tmp_path: Path) -> None:
    assert json.loads(file_of(tmp_path, "/").body)["detail"] == NOT_BUILT


def test_the_page_reads_its_agent_and_no_captcha_here_and_is_only_read(tmp_path: Path) -> None:
    config = got(paging(tmp_path), "/pinecall/config")
    assert json.loads(config.body) == {"agent": "front-desk", "turnstile": None}
    assert posted(paging(tmp_path), "/elsewhere", b"{}").status == 405


def test_a_ticket_the_gateway_could_not_be_asked_for_is_a_502(tmp_path: Path) -> None:
    assert posted(paging(tmp_path), "/pinecall/token", b'{"scope": "chat"}').status == 502
