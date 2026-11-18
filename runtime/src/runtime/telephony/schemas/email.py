"""The bodies of the email endpoints: the org's layout, read and written, and a reply as it would be set in it."""

from typing import Annotated

from pydantic import Field

from runtime.kit.schemas import Row, Schema

# As the layout's own rule says it: a layout is a page, not a site.
LONGEST = 200_000


class EmailLayoutRow(Row):
    """GET /v1/org/email/layout: the HTML an agent's email is set in, and whether it is the org's own."""

    html: str
    own: bool


class PutEmailLayout(Schema):
    """PUT /v1/org/email/layout: the org's HTML, saying once with `{{content}}` where the reply goes."""

    html: Annotated[str, Field(min_length=1, max_length=LONGEST)]


class PreviewEmail(Schema):
    """POST /v1/org/email/layout/preview: words as an agent would write them, and the subject they answer."""

    text: Annotated[str, Field(min_length=1, max_length=8000)]
    subject: Annotated[str, Field(max_length=300)] = "Your message"
    # A layout to try before it is kept; the org's own (or the plain one) when left out.
    html: Annotated[str | None, Field(default=None, max_length=LONGEST)] = None


class PreviewedEmail(Row):
    """The reply as the contact would read it: its subject, its HTML in the layout, and its plain part."""

    subject: str
    html: str
    text: str
