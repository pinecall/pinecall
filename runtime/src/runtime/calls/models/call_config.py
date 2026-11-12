"""A resolved declaration a call ran on, kept once per org under the hash of its JSON."""

from typing import Any

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model


# The table and its column say `config`, the word of the release that made them; what they hold is a
# declaration with the org's settings laid under it, as a call ran it.
class CallConfig(Model):
    """Most calls of an agent run on a handful of these."""

    __tablename__ = "call_configs"
    __kept__ = Kept(
        not_exported=(
            "what a call ran on, kept so the box can serve the call again: an export carries the org's "
            "settings as it set them"
        )
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
