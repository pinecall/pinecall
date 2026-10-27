"""The model's notes on an output are read back checked: each in one line of it, one a line, the rest dropped."""

from pinecall_runtime.agents.service.explain import Note, notes_of

OUTPUT = (
    "  org lesson · key k_1234 · sandbox · berna-air · production: yes\n  a person's key: the sandbox without --prod"
)


def test_a_note_names_a_line_by_a_fragment_of_it_in_any_case_and_spacing() -> None:
    answer = '[{"find": "ORG  lesson", "say": "Tu org es lesson."}, {"find": "person\'s key", "say": "Es de persona."}]'
    assert notes_of(answer, OUTPUT) == [
        Note("ORG  lesson", "Tu org es lesson."),
        Note("person's key", "Es de persona."),
    ]


def test_a_fence_is_forgiven_and_what_is_not_notes_is_dropped() -> None:
    fenced = (
        '```json\n[{"find": "sandbox without", "say": "Sin prod, el sandbox."}, {"find": "made up", "say": "x"}, '
        '"junk", {"find": "org lesson"}]\n```'
    )
    assert notes_of(fenced, OUTPUT) == [Note("sandbox without", "Sin prod, el sandbox.")]
    assert notes_of("I cannot help with that.", OUTPUT) == []
    assert notes_of('{"find": "org lesson", "say": "an object, not a list"}', OUTPUT) == []


def test_one_note_a_line_and_most_at_most() -> None:
    answer = (
        '[{"find": "org lesson", "say": "One."}, {"find": "key k_1234", "say": "Same line again."}, '
        '{"find": "--prod", "say": "Two."}]'
    )
    assert [note.say for note in notes_of(answer, OUTPUT)] == ["One.", "Two."]
    assert [note.say for note in notes_of(answer, OUTPUT, most=1)] == ["One."]
