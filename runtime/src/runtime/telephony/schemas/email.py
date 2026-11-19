"""The bodies of the email endpoints: the org's layout, read and written, and a reply as it would be set in it."""

from typing import Annotated

from pydantic import Field

from runtime.kit.schemas import Row, Schema

# As the layout's own rule says it: a layout is a page, not a site.
LONGEST = 200_000


class EmailLayoutRow(Row):
    """GET /v1/org/email/layout: the HTML an email is set in, whether it is the org's own, whether it is text alone."""

    html: str
    own: bool
    # The org chose no HTML at all: `html` is then the plain layout, which nothing is set in.
    text_only: bool = False


class PutEmailLayout(Schema):
    """PUT /v1/org/email/layout: the org's HTML, `{{content}}` once where the reply goes; or `text_only` and no HTML."""

    html: Annotated[str | None, Field(default=None, min_length=1, max_length=LONGEST)] = None
    # The org's emails go as text alone, one `text/plain` part: said without `html`.
    text_only: bool = False


class PreviewEmail(Schema):
    """POST /v1/org/email/layout/preview: words as an agent would write them, and the subject they answer."""

    text: Annotated[str, Field(min_length=1, max_length=8000)]
    subject: Annotated[str, Field(max_length=300)] = "Your message"
    # A layout to try before it is kept; the org's own (or the plain one) when left out.
    html: Annotated[str | None, Field(default=None, max_length=LONGEST)] = None
    # Try the email as text alone, whatever the org keeps; left out, as the org keeps it.
    text_only: bool | None = None
    # Try it in the plain layout, the one of an org that keeps none, whatever the org keeps.
    plain: bool = False


class PreviewedEmail(Row):
    """The reply as the contact would read it: its subject, its HTML in the layout (none as text alone), its text."""

    subject: str
    html: str | None
    text: str
