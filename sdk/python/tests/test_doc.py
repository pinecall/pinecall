"""A docstring as the model reads it: one line, ending at the first section, and its `Args:`."""

from pinecall._doc import arguments_of, one_line

DOC = """Busca al paciente.

    Pide los dos antes de llamarla.

    Args:
        name: el nombre completo,
            como lo dijo
        phone (str): el teléfono
            day: not a parameter, a continuation

    Returns:
        la ficha
    """


def test_the_description_is_one_line_its_blank_lines_dropped_ending_at_the_first_section() -> None:
    assert one_line(DOC) == "Busca al paciente. Pide los dos antes de llamarla."


def test_no_docstring_or_an_empty_one_is_no_description() -> None:
    assert one_line(None) is None
    assert one_line("   \n  ") is None


def test_each_parameter_is_what_args_says_its_continuation_joined() -> None:
    assert arguments_of(DOC) == {
        "name": "el nombre completo, como lo dijo",
        "phone": "el teléfono day: not a parameter, a continuation",
    }


def test_a_docstring_with_no_args_section_describes_no_parameter() -> None:
    assert arguments_of("Solo una frase.") == {}
