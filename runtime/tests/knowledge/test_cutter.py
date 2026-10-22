"""The cutter: no comment reaches a chunk, an `asks` comment gives the section its questions, a fence keeps its own."""

from pinecall_runtime.knowledge.service.cutter import HEADING_SEPARATOR, chunks_of, cut

PRICES = """# Prices

<!-- asks
How much does a check-up cost?
Is the first visit free?
-->

A check-up is forty euros. <!-- the 2024 price -->

## Insurance

<!-- asks
Do you take insurance?

-->
We take every insurer.
"""

CODE = """# Install

```html
<!-- the widget -->
<script src="widget.js"></script>
```
"""


def test_a_comment_is_dropped_and_an_asks_comment_gives_the_section_its_questions() -> None:
    """The author's note is not in the chunk; the questions are the first piece's, one a line."""
    prices, insurance = chunks_of("prices.md", PRICES)
    assert prices.text == "A check-up is forty euros."
    assert prices.asks == ("How much does a check-up cost?", "Is the first visit free?")
    assert insurance.heading == HEADING_SEPARATOR.join(("Prices", "Insurance"))
    assert insurance.text == "We take every insurer."
    assert insurance.asks == ("Do you take insurance?",)


def test_a_comment_inside_a_code_fence_is_code_and_stays() -> None:
    """A fenced HTML example keeps its comment: the chunker reads code as code."""
    (install,) = chunks_of("install.md", CODE)
    assert "<!-- the widget -->" in install.text
    assert install.asks == ()


def test_a_file_counts_its_pieces_and_their_questions_as_rows() -> None:
    """Three questions over two pieces: five rows against the quota."""
    assert cut("prices.md", PRICES).rows == 5
    assert cut("install.md", CODE).rows == 1


def test_a_file_from_windows_is_read_as_one_text_and_its_front_matter_goes() -> None:
    """CRLF is LF: the front matter is dropped, the hash is the LF file's, and the pieces are the same."""
    front = "---\ntitle: Prices\n---\n\n" + PRICES
    assert cut("prices.md", front.replace("\n", "\r\n")) == cut("prices.md", front)
    assert [piece.text for piece in cut("prices.md", front.replace("\n", "\r\n")).pieces] == [
        "A check-up is forty euros.",
        "We take every insurer.",
    ]


def test_a_comment_opened_in_one_section_and_closed_in_the_next_reaches_neither() -> None:
    """The author hid both halves and the heading between them: one section, no `<!--`, `-->` or draft in it."""
    crossing = "# Prices\n\nForty euros. <!-- draft:\n\n## Insurance\n\nnot yet --> We take every insurer.\n"
    [prices] = chunks_of("prices.md", crossing)
    assert prices.heading == "Prices"
    assert "draft" not in prices.text and "<!--" not in prices.text and "-->" not in prices.text
    assert prices.text.startswith("Forty euros.") and prices.text.endswith("We take every insurer.")
