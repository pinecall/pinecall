"""The HTML an agent's email is set in: the org's layout or the plain one, and the reply's words as safe HTML."""

import pytest

from runtime.exceptions import ValidationError
from runtime.telephony.service import email_layout
from runtime.telephony.service.email_layout import CONTENT, PLAIN


def test_the_replys_marks_are_read_and_anything_else_is_text() -> None:
    """Paragraphs, a list, bold, a link; a tag a model or a contact wrote is escaped, never HTML."""
    written = "Hola Ana,\n\nTenemos:\n\n- **sábado** 10 a 14\n- domingo cerrado\n\nReservá en [la web](https://acme.example/r).\n<script>x</script>"
    html = email_layout.html_of(written)
    assert '<p style="margin:0 0 14px;">Hola Ana,</p>' in html
    assert "<ul><li><strong>sábado</strong> 10 a 14</li><li>domingo cerrado</li></ul>" in html
    assert '<a href="https://acme.example/r">la web</a>' in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_a_link_cannot_carry_an_attribute_of_its_own() -> None:
    """A quote in an address is escaped: the href is the address and nothing more."""
    html = email_layout.html_of('[x](https://a.example/"onmouseover="alert(1))')
    assert 'onmouseover="' not in html


def test_a_layout_says_once_where_the_reply_goes_and_the_subject_is_escaped_wherever_it_is_asked_for() -> None:
    """One {{content}}; the subject set in as text; the plain layout is a layout too."""
    for wrong in ("<p>no place</p>", f"{CONTENT}{CONTENT}"):
        with pytest.raises(ValidationError, match="says once"):
            email_layout.check_layout(wrong)
    assert email_layout.check_layout(PLAIN) == PLAIN
    set_in = email_layout.set_in("<h1>{{subject}}</h1>{{content}}", "Hola", subject="Re: <Horarios>")
    assert set_in == '<h1>Re: &lt;Horarios&gt;</h1><p style="margin:0 0 14px;">Hola</p>'


def test_the_plain_part_says_the_words_without_their_marks() -> None:
    """Bold and italics taken off, a link's address beside its words."""
    assert (
        email_layout.text_of("**Sí**, *mañana*: [reservá](https://acme.example)")
        == "Sí, mañana: reservá (https://acme.example)"
    )
