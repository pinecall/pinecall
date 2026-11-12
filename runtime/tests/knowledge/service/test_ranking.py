"""What is done with the hits of a hybrid search: scores relative to the best, the best first, ties by id."""

from runtime.knowledge.repository.search import Hit
from runtime.knowledge.service.ranking import relative_to_the_best


def a_hit(named: str, fused: float, cosine: float = 0.5) -> Hit[None]:
    """A hit with no columns."""
    return Hit(id=named, fused=fused, cosine=cosine, row=None)


def test_the_best_is_one_and_the_rest_are_their_share_of_it_best_first() -> None:
    """Scores are relative to the best hit."""
    scored = relative_to_the_best([a_hit("b", 0.5), a_hit("a", 1.0), a_hit("c", 0.25)])
    assert [(hit.id, hit.fused) for hit in scored] == [("a", 1.0), ("b", 0.5), ("c", 0.25)]


def test_a_tie_is_ordered_by_id_so_two_processes_answer_alike() -> None:
    """Equal scores come back in one order everywhere."""
    tied = relative_to_the_best([a_hit("z", 1.0), a_hit("m", 1.0)])
    assert [hit.id for hit in tied] == ["m", "z"]


def test_nothing_found_is_nothing_and_a_zero_best_divides_nothing() -> None:
    """No hits, or a best of zero, never divides by zero."""
    assert relative_to_the_best([]) == []
    assert [hit.fused for hit in relative_to_the_best([a_hit("a", 0.0)])] == [0.0]
