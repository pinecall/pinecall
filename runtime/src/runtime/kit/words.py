"""Whole words found and replaced, in a text and in a stream: the longest form first, in any case."""

import re
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Mapping

# A form that begins or ends with a letter or a digit is found only where a word begins or ends, so
# `CLI` is said its way in "el CLI," and never inside "cliente"; a form that spans words ("Dr. Lee")
# is found across them. A stream is replaced chunk by chunk (`replace_in_stream`), a whole text at once
# (`replace_words`): both find the same words.


def pattern_of(written: Iterable[str]) -> re.Pattern[str] | None:
    """The written forms as one pattern, the longest first, each bound as a whole word; None for none."""
    forms = sorted({form for form in written if form}, key=len, reverse=True)
    if not forms:
        return None

    def bound(form: str) -> str:
        start = r"(?<!\w)" if re.match(r"\w", form) else ""
        end = r"(?!\w)" if re.search(r"\w$", form) else ""
        return f"{start}{re.escape(form)}{end}"

    return re.compile("|".join(bound(form) for form in forms), re.IGNORECASE)


def holds(text: str, written: str) -> bool:
    """Whether the text holds the written form, as a whole word."""
    pattern = pattern_of([written])
    return pattern is not None and pattern.search(text) is not None


def replace_words(text: str, says: Mapping[str, str]) -> str:
    """The text with each written form replaced by how it is said."""
    pattern = pattern_of(says)
    if pattern is None:
        return text
    spoken = {written.lower(): form for written, form in says.items() if written}
    return pattern.sub(lambda found: spoken[found.group(0).lower()], text)


# The last words are held until the next chunk, as many as the longest form has: a word cut between
# two chunks, or a form that spans words, is found whole.
def replace_in_stream(says: Mapping[str, str]) -> Callable[[AsyncIterable[str]], AsyncIterable[str]]:
    """A transform of a stream of text: each written form replaced, a form never cut in two."""
    pattern = pattern_of(says)
    reach = max((len(written.split()) for written in says if written), default=1)

    async def transform(chunks: AsyncIterable[str]) -> AsyncIterator[str]:
        held = ""
        async for chunk in chunks:
            if pattern is None:
                yield chunk
                continue
            held += chunk
            words = list(re.finditer(r"\S+", held))
            if len(words) <= reach:
                continue
            cut = words[-reach].start()
            for found in pattern.finditer(held):
                if found.start() < cut < found.end():
                    cut = found.start()
            if cut > 0:
                yield replace_words(held[:cut], says)
                held = held[cut:]
        if held:
            yield replace_words(held, says)

    return transform


class Unsaying:
    """The spoken forms of a lexicon, matched as the written words were replaced, and read back as written."""

    def __init__(self, says: Mapping[str, str]) -> None:
        """Every spoken form, longest first, mapped back to the word written."""
        self.written = {spoken.lower(): word for word, spoken in says.items() if spoken}
        keys = sorted(self.written, key=len, reverse=True)
        self.pattern = re.compile("|".join(re.escape(key) for key in keys), re.IGNORECASE)
        prefixes = {key[:n] for key in keys for n in range(1, len(key))}
        self.started = (
            re.compile("(?:" + "|".join(re.escape(p) for p in prefixes) + r")\Z", re.IGNORECASE) if prefixes else None
        )

    def back(self, text: str) -> str:
        """The text with every spoken form put back as the word written."""
        return self.pattern.sub(lambda found: self.written[found.group(0).lower()], text)

    def may_go_on(self, text: str) -> bool:
        """Whether the text ends in what the next piece could complete into a spoken form."""
        return self.started is not None and self.started.search(text) is not None

    def found(self, text: str) -> bool:
        """Whether the text holds a spoken form."""
        return self.pattern.search(text) is not None
