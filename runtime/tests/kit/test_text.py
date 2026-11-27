"""A name makes a slug: accents dropped, words joined by dashes, and a name with no letters makes none."""

import pytest

from runtime.exceptions import ValidationError
from runtime.kit.text import cut_in_parts, estimate_tokens, parse_address, parse_slug, slug_of


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


def test_a_text_is_estimated_at_its_words_times_one_point_three() -> None:
    assert estimate_tokens("una dos tres cuatro cinco seis siete ocho nueve diez") == 13
    assert estimate_tokens("") == 0


def test_a_text_longer_than_a_channel_takes_is_cut_where_the_writing_breathes() -> None:
    """Each part is within the limit, nothing is lost, and a paragraph is never cut in two when it fits."""
    first, second = "a" * 3000, "b " * 1500
    assert cut_in_parts(f"{first}\n\n{second}", 4096) == [first, second.strip()]
    assert all(len(part) <= 4096 for part in cut_in_parts("palabra " * 3000, 4096))
    assert "".join(cut_in_parts("x" * 9000, 4096)) == "x" * 9000
    assert cut_in_parts("hola", 4096) == ["hola"]
    assert cut_in_parts("uno dos tres", 8) == ["uno dos", "tres"]


@pytest.mark.parametrize(
    ("written", "kept"),
    [
        ("+59829001199", "+59829001199"),
        ("help@acme.com", "help@acme.com"),
        ("messenger:7001234567", "messenger:7001234567"),
        ("instagram:7001234567", "instagram:7001234567"),
    ],
)
def test_a_route_or_a_contact_is_a_number_an_email_or_metas_id_of_a_contact(written: str, kept: str) -> None:
    assert parse_address(written) == kept


def test_metas_id_of_a_page_is_an_address_only_where_the_channel_asked_answers_at_such_ids() -> None:
    assert parse_address(" 1472943555898656 ", by_meta_id=True) == "1472943555898656"
    with pytest.raises(ValidationError, match=r"E\.164"):
        parse_address("1472943555898656")
    with pytest.raises(ValidationError, match="digits alone"):
        parse_address("+59829001199", by_meta_id=True)


@pytest.mark.parametrize("written", ["facebook:7001234567", "messenger:abc", "1234", "59829001199"])
def test_neither_a_number_nor_metas_id_is_refused(written: str) -> None:
    with pytest.raises(ValidationError):
        parse_address(written)
