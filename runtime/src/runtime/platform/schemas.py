"""The bodies of the platform's endpoints: the box's brand read and changed."""

from runtime.kit.schemas import Row, Schema


class BrandRow(Row):
    """What the box's pages and emails are called and painted with."""

    name: str
    logo_url: str | None
    accent: str


class PutBrand(Schema):
    """PUT /v1/ops/brand: a field left out keeps its value; an empty one goes to the default."""

    name: str | None = None
    logo_url: str | None = None
    accent: str | None = None
