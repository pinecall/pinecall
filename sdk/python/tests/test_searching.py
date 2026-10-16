"""Whether a class searches its bases, read off its file: a call counts, the words do not."""

import importlib.util
import sys
from pathlib import Path

import pytest

from pinecall import Agent
from pinecall._searching import in_source, searches


def test_a_tool_that_searches_the_knowledge_counts() -> None:
    assert in_source("def hours(self, q):\n    return self.knowledge.search(q, k=3)\n")


def test_a_search_through_the_call_counts_too() -> None:
    assert in_source("call.search(q)")
    assert in_source("self.call.search(q)")


def test_the_words_in_a_comment_or_a_string_do_not() -> None:
    assert not in_source('# knowledge.search the bases\nsaid = "knowledge.search(q)"\n')


def test_a_search_of_something_else_does_not() -> None:
    assert not in_source("re.search(pattern, text)\nself.index.search(q)\n")


def test_a_class_is_read_off_the_file_it_was_written_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = tmp_path / "horario.py"
    written.write_text(
        '"""Un agente que busca."""\n'
        "from pinecall import Agent\n\n"
        "class Horario(Agent):\n"
        '    """Dice el horario."""\n\n'
        "    def hours(self, q: str) -> object:\n"
        "        return self.knowledge.search(q)\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("horario", written)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # As an import does: the module is in sys.modules before its body runs.
    monkeypatch.setitem(sys.modules, "horario", module)
    spec.loader.exec_module(module)
    assert searches(module.Horario)


def test_a_class_that_never_searches_says_so() -> None:
    class Callada(Agent):
        """No busca nada."""

    assert not searches(Callada)
