"""A golden scored by code: the first chunk that answers counts, and any of the paths a question names answers."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.knowledge.service import bases
from runtime.knowledge.service.base_golden import Answered, Question, run, score_answers
from runtime.knowledge.service.embedder import Embedder
from runtime.knowledge.service.search import Found
from tests.conftest import needs_the_database
from tests.fakes.embeddings import Embeddings


def a_hit(path: str, heading: str | None = None) -> Found:
    """A chunk found, its scores immaterial."""
    return Found(id=path, base="docs", path=path, heading=heading, text="", score=1.0)


def test_any_of_the_paths_a_question_names_answers_it() -> None:
    """The FAQ's line and the guide are both right: whichever came back first is the rank."""
    asked = Answered(
        Question("how much?", ("prices.md", "faq.md")), [a_hit("hours.md"), a_hit("faq.md"), a_hit("prices.md")]
    )
    score = score_answers([asked], k=4)
    assert score.recall_at_k == 1.0
    assert score.misses == []


def test_a_question_none_of_whose_paths_came_back_is_a_miss() -> None:
    """Two right pages, neither found: one miss, naming both."""
    asked = Answered(Question("how much?", ("prices.md", "faq.md")), [a_hit("hours.md")])
    score = score_answers([asked], k=4)
    assert score.recall_at_k == 0.0
    assert [miss.expects for miss in score.misses] == [("prices.md", "faq.md")]


def test_a_heading_answers_for_its_section_and_what_is_under_it_and_a_file_for_every_chunk() -> None:
    """A heading answers what is under it, a file any chunk of it, and `prices-2024.md` is not `prices.md`."""
    under = a_hit("prices.md", "Prices › Check-up")
    assert score_answers([Answered(Question("q", ("prices.md › Prices",)), [under])], k=1).recall_at_k == 1.0
    assert score_answers([Answered(Question("q", ("prices.md",)), [under])], k=1).recall_at_k == 1.0
    assert score_answers([Answered(Question("q", ("prices.md",)), [a_hit("prices-2024.md")])], k=1).recall_at_k == 0.0


@needs_the_database
async def test_a_golden_embeds_its_questions_in_one_request_and_scores_each(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, vendor: Embeddings, scope: Scope
) -> None:
    """Three questions are one trip to the embedder, and each is scored against what it found."""
    folder = [
        ("precios.md", "# Precios\n\nUna limpieza cuesta 40 euros.\n"),
        ("horario.md", "# Horario\n\nAbrimos de lunes a viernes.\n"),
    ]
    await bases.push_folder(sessions, embedder, scope, "clinica", folder, language=None, replace=True)
    before = len(vendor.requests)
    questions = [
        Question("cuánto cuesta una limpieza", ("precios.md",)),
        Question("qué días abren", ("horario.md",)),
        Question("hacen ortodoncia", ("ortodoncia.md",)),
    ]
    score = await run(sessions, embedder, scope, "clinica", questions, k=2)
    assert len(vendor.requests) == before + 1
    assert score.questions == 3
    assert [miss.asks for miss in score.misses] == ["hacen ortodoncia"]
