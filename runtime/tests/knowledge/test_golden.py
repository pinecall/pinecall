"""A golden scored by code: the first chunk that answers counts, and any of the paths a question names answers."""

from pinecall_runtime.knowledge.service.bases import Answered, Found, Question, score_docs


def a_hit(path: str, heading: str | None = None) -> Found:
    """A chunk found, its scores immaterial."""
    return Found(id=path, base="docs", path=path, heading=heading, text="", score=1.0, cosine=0.5)


def test_any_of_the_paths_a_question_names_answers_it() -> None:
    """The FAQ's line and the guide are both right: whichever came back first is the rank."""
    asked = Answered(
        Question("how much?", ("prices.md", "faq.md")), [a_hit("hours.md"), a_hit("faq.md"), a_hit("prices.md")]
    )
    score = score_docs([asked], k=4)
    assert score.figures.recall_at_k == 1.0
    assert score.misses == []


def test_a_question_none_of_whose_paths_came_back_is_a_miss() -> None:
    """Two right pages, neither found: one miss, naming both."""
    asked = Answered(Question("how much?", ("prices.md", "faq.md")), [a_hit("hours.md")])
    score = score_docs([asked], k=4)
    assert score.figures.recall_at_k == 0.0
    assert [miss.question.expects for miss in score.misses] == [("prices.md", "faq.md")]


def test_a_heading_answers_for_its_section_and_what_is_under_it_and_a_file_for_every_chunk() -> None:
    """A heading answers what is under it, a file any chunk of it, and `prices-2024.md` is not `prices.md`."""
    under = a_hit("prices.md", "Prices › Check-up")
    assert score_docs([Answered(Question("q", ("prices.md › Prices",)), [under])], k=1).figures.recall_at_k == 1.0
    assert score_docs([Answered(Question("q", ("prices.md",)), [under])], k=1).figures.recall_at_k == 1.0
    assert (
        score_docs([Answered(Question("q", ("prices.md",)), [a_hit("prices-2024.md")])], k=1).figures.recall_at_k == 0.0
    )
