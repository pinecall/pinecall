"""`serve prompt`: the class's prompt in the state asked for, and which tools it shows, offline."""

import io
from pathlib import Path

from pinecall.serve._loading import parse
from pinecall.serve._prompting import prompt
from tests.fakes.project import written


def printed(tmp_path: Path, *flags: str) -> str:
    out = io.StringIO()
    file = written(tmp_path)
    assert prompt(parse(["--file", str(file), "--slug", "recepcion", *flags]), out) == 0
    return out.getvalue()


def test_the_page_is_every_block_under_its_header_in_the_channel_asked_for(tmp_path: Path) -> None:
    page = printed(tmp_path, "--channel", "whatsapp")
    assert "── identity (static) ──" in page
    assert "You are on WhatsApp." in page
    assert page.rstrip().endswith("Pide el nombre.")


def test_a_state_given_field_by_field_is_the_one_the_view_reads(tmp_path: Path) -> None:
    page = printed(tmp_path, "--state", 'patient="Ana"', "--state", 'stage="book"')
    assert page.rstrip().endswith("Hablas con Ana.")


def test_the_machine_marks_what_this_state_shows_and_what_gates_the_rest(tmp_path: Path) -> None:
    page = printed(tmp_path, "--show-machine")
    machine = page[page.index("── tools ── stage: identify") :].splitlines()
    assert machine[2:] == ["  ● find_patient  identify", "  ○ book          book"]
