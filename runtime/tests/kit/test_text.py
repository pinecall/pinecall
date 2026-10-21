"""A name makes a slug: accents dropped, words joined by dashes, and a name with no letters makes none."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import parse_slug, slug_of


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Clínica Norte", "clinica-norte"),
        ("  Brightside  Dental, S.A. ", "brightside-dental-s-a"),
        ("Müller & Söhne GmbH", "muller-sohne-gmbh"),
        ("acme", "acme"),
    ],
)
def test_a_name_makes_the_slug_the_page_used_to(name: str, slug: str) -> None:
    """The slug is what the sign-up page derived before the gateway did: the same org by the same name."""
    assert slug_of(name) == slug
    assert parse_slug(slug_of(name)) == slug


def test_a_long_name_is_cut_at_a_slugs_length_and_never_ends_in_a_dash() -> None:
    """Sixty-three characters at most, and a cut that lands on a dash drops it."""
    made = slug_of("word " * 40)
    assert len(made) <= 63 and not made.endswith("-")
    assert parse_slug(made) == made


def test_a_name_with_no_letters_or_digits_makes_no_slug() -> None:
    """Nothing to call the org by is refused in words, not an empty slug."""
    with pytest.raises(ValidationError, match="letters and digits"):
        slug_of("¡¡¡ ---")
