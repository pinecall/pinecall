"""A recorded line's words: grouped where the lexicon touches them, timed by the voice, or spread by their length."""

from pinecall_runtime.agents.service.lines import Group, groups_of, line_id, words_of
from pinecall_runtime.providers import service as providers

CARTESIA = providers.Running(vendor="cartesia", credentials={}, model="sonic-3", voice="f786b574", language="en")


def timed(*said: tuple[str, float, float]) -> list[providers.TimedWord]:
    """The words a voice timed, as it gives them."""
    return [providers.TimedWord(text=text, start_s=start, end_s=end) for text, start, end in said]


def test_with_no_lexicon_each_written_word_is_said_as_written() -> None:
    assert groups_of("Up here are our services.", {}) == [
        Group(("Up",), "Up"),
        Group(("here",), "here"),
        Group(("are",), "are"),
        Group(("our",), "our"),
        Group(("services.",), "services."),
    ]


def test_a_lexicon_form_is_said_as_a_whole_word_and_across_words_as_one_group() -> None:
    says = {"Pinecall": "pine call", "Dr. Lee": "Doctor Lee", "CLI": "ci el ái"}

    assert groups_of("Pinecall's front desk", says)[0] == Group(("Pinecall's",), "pine call's")
    assert groups_of("el CLI y un cliente", says) == [
        Group(("el",), "el"),
        Group(("CLI",), "ci el ái"),
        Group(("y",), "y"),
        Group(("un",), "un"),
        Group(("cliente",), "cliente"),
    ]
    assert groups_of("Ask Dr. Lee today", says) == [
        Group(("Ask",), "Ask"),
        Group(("Dr.", "Lee"), "Doctor Lee"),
        Group(("today",), "today"),
    ]


def test_the_voices_times_go_to_the_written_words_a_form_of_two_spoken_words_taking_both() -> None:
    groups = groups_of("Welcome to Pinecall today", {"Pinecall": "pine call"})
    said = timed(("Welcome", 0.1, 0.5), ("to", 0.5, 0.6), ("pine", 0.6, 0.8), ("call", 0.8, 1.1), ("today", 1.1, 1.5))

    words, was_timed = words_of(groups, said, 1600)

    assert was_timed
    assert words == [
        {"text": "Welcome", "start_ms": 100, "end_ms": 500},
        {"text": "to", "start_ms": 500, "end_ms": 600},
        {"text": "Pinecall", "start_ms": 600, "end_ms": 1100},
        {"text": "today", "start_ms": 1100, "end_ms": 1500},
    ]


def test_a_voice_that_times_nothing_or_otherwise_has_each_word_placed_by_its_length() -> None:
    groups = groups_of("one three", {})

    for said in ([], timed(("one", 0, 0.2))):
        words, was_timed = words_of(groups, said, 1000)
        assert not was_timed
        assert [word["text"] for word in words] == ["one", "three"]
        assert words[0]["start_ms"] == 0 and words[0]["end_ms"] == words[1]["start_ms"]
        assert words[-1]["end_ms"] == 1000


def test_a_line_is_kept_by_its_voice_its_lexicon_forms_and_its_text() -> None:
    first = line_id(CARTESIA, {}, "Up here.")

    assert line_id(CARTESIA, {}, "Up here.") == first
    assert line_id(CARTESIA, {"Pinecall": "pine call"}, "Up here.") == first
    assert line_id(CARTESIA, {"here": "hear"}, "Up here.") != first
    assert line_id(providers.Running(vendor="cartesia", credentials={}, voice="other"), {}, "Up here.") != first
    assert line_id(CARTESIA, {}, "Up there.") != first
