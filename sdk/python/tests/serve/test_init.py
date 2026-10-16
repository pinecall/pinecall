"""The entry: a verb it knows runs, anything else is its usage; what cannot run says why, with 2."""

import io
from pathlib import Path

from pinecall.serve import main
from tests.fakes.project import written


def ran(argv: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    status = main(argv, out=out, err=err, env=env or {})
    return status, out.getvalue(), err.getvalue()


def test_a_verb_it_does_not_know_prints_the_usage_and_exits_2() -> None:
    status, _, err = ran(["listen"])
    assert status == 2
    assert err.startswith("usage: python -m pinecall.serve start")


def test_prompt_prints_the_page_and_exits_0(tmp_path: Path) -> None:
    status, out, _ = ran(["prompt", "--file", str(written(tmp_path)), "--slug", "recepcion"])
    assert status == 0
    assert "── view (dynamic) ──" in out


def test_start_with_no_door_in_the_environment_says_so_and_exits_2(tmp_path: Path) -> None:
    status, _, err = ran(["start", "--file", str(written(tmp_path)), "--slug", "recepcion"])
    assert (status, err.strip()) == (
        2,
        "serve start reads PINECALL_URL and PINECALL_KEY from its environment, and one was not set",
    )


def test_a_class_the_gateway_would_refuse_is_refused_before_anything_is_dialled(
    tmp_path: Path,
) -> None:
    file = written(tmp_path)
    file.write_text(
        file.read_text().replace('    """Eres', '    language: str = "es"\n    """Eres'),
        encoding="utf-8",
    )
    status, _, err = ran(["prompt", "--file", str(file), "--slug", "recepcion"])
    assert status == 2
    assert "`language` is the class's, not a call's state" in err
