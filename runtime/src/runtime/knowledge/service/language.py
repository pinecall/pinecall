"""The language a base is read in: a text-search configuration Postgres ships, said or counted from its words."""

import re
from collections import Counter

from runtime.exceptions import ValidationError
from runtime.knowledge.models import Language

# What a base whose words say no language clearly is read in: `simple` stems nothing.
UNDECIDED = Language.simple
# A push may say the language as its ISO code or as the configuration's name.
BY_CODE: dict[str, Language] = {
    "en": Language.english,
    "es": Language.spanish,
    "pt": Language.portuguese,
    "fr": Language.french,
    "de": Language.german,
    "it": Language.italian,
    "nl": Language.dutch,
}
BY_NAME: dict[str, Language] = {language.value: language for language in Language}


def _words(said: str) -> frozenset[str]:
    return frozenset(said.split())


# The function words a text in each language is full of. Only the ones no other language here
# shares count (`de` is Spanish, Portuguese and French; `y` and `los` are Spanish alone), so a
# short Spanish text is never read as Portuguese for the words the two have in common.
STOPWORDS: dict[Language, frozenset[str]] = {
    Language.english: _words(
        "the and of to in is that it for with as on are this be at from or by an not was but have has "
        "its which their when what can will if"
    ),
    Language.spanish: _words(
        "el la de que y en los del se las por un para con una su al lo como más pero sus también sin "
        "cuando esta este hay donde cada ya"
    ),
    Language.portuguese: _words(
        "o a de que e do da em um para é com não uma os no se na por mais as dos como mas ao das seu "
        "sua ou quando já também pelo"
    ),
    Language.french: _words(
        "le de et la les des en un une du que est pour qui dans pas sur au ce il plus ne se par vous "
        "nous sont avec ou cette aux"
    ),
    Language.german: _words(
        "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch es an "
        "werden aus er hat dass sie nach"
    ),
    Language.italian: _words(
        "di che e la il un a per in una è non le si con sono da del come anche più ma della nel gli "
        "alla dei questo essere al"
    ),
    Language.dutch: _words(
        "de het een en van in is dat op te zijn met voor niet aan er ook als bij maar om dan nog "
        "worden wordt uit naar door kan"
    ),
    Language.simple: frozenset(),
}
EXCLUSIVE: dict[Language, frozenset[str]] = {
    language: words - frozenset().union(*(other for name, other in STOPWORDS.items() if name != language))
    for language, words in STOPWORDS.items()
}
# A word is a whole run of letters: the letters inside a code or a count (`Y8` is not the Spanish
# `y`, `2nd` is not `nd`) say nothing of the language. The 2026-10-23 eval's table of rates was
# counted Spanish for the one `Y8` in its last row.
A_WORD = re.compile(r"(?<!\w)[^\W\d_]+(?!\w)")
# Under this share of a language's own function words no language is said: a tariff table, a list
# of names.
LEAST_SHARE = 0.02
# The best language must lead the second by this much of the words, or neither is believed.
LEAST_LEAD = 0.01
LONGEST_SAMPLE = 20_000


def parse_language(said: str | None) -> Language | None:
    """A language a push names, by its code or its name; None when it names none."""
    if said is None:
        return None
    word = said.strip().lower()
    found = BY_CODE.get(word) or BY_NAME.get(word)
    if found is None:
        raise ValidationError(
            f"a base's language is one of {', '.join(BY_NAME)} or its code ({', '.join(BY_CODE)}), not {said!r}"
        )
    return found


def detect_language(texts: list[str]) -> Language:
    """The language the texts' function words say, or `simple` when they do not say one clearly."""
    words = A_WORD.findall(" ".join(text[:LONGEST_SAMPLE] for text in texts).lower())
    if not words:
        return UNDECIDED
    counted = Counter(words)
    shares: list[tuple[float, Language]] = sorted(
        ((sum(counted[word] for word in EXCLUSIVE[language]) / len(words), language) for language in Language),
        reverse=True,
    )
    (best, language), (second, _) = shares[0], shares[1]
    if best < LEAST_SHARE or best - second < LEAST_LEAD:
        return UNDECIDED
    return language
