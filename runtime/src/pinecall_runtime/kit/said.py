"""How the lexicon's words are said: each written form found as a whole word, the longest first, in any case."""

import re
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Mapping

# A form that begins or ends with a letter or a digit is found only where a word begins or ends, so
# `CLI` is said its way in "el CLI," and never inside "cliente"; a form that spans words ("Dr. Lee")
# is found across them. A call's voice says a stream (`saying`), a recorded line a whole text
# (`pattern_of`): both find the same words.


def pattern_of(written: Iterable[str]) -> re.Pattern[str] | None:
    """The written forms as one pattern, the longest first, each bounded as a whole word; None for none."""
    forms = sorted({form for form in written if form}, key=len, reverse=True)
    if not forms:
        return None

    def bounded(form: str) -> str:
        start = r"(?<!\w)" if re.match(r"\w", form) else ""
        end = r"(?!\w)" if re.search(r"\w$", form) else ""
        return f"{start}{re.escape(form)}{end}"

    return re.compile("|".join(bounded(form) for form in forms), re.IGNORECASE)


def holds(text: str, written: str) -> bool:
    """Whether the text holds the written form, as a whole word."""
    pattern = pattern_of([written])
    return pattern is not None and pattern.search(text) is not None


def said(text: str, says: Mapping[str, str]) -> str:
    """The text with each written form replaced by how it is said."""
    pattern = pattern_of(says)
    if pattern is None:
        return text
    spoken = {written.lower(): form for written, form in says.items() if written}
    return pattern.sub(lambda found: spoken[found.group(0).lower()], text)


def saying(says: Mapping[str, str]) -> Callable[[AsyncIterable[str]], AsyncIterable[str]]:
    """A call's voice's text transform: the stream said with the lexicon's words, a form never cut in two.

    The last words are held until the next chunk, as many as the longest form has: a word cut between
    two chunks, or a form that spans words, is found whole."""
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
                yield said(held[:cut], says)
                held = held[cut:]
        if held:
            yield said(held, says)

    return transform
