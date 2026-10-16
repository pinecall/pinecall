"""A resolved agent config a call ran on, kept once per org under the hash of its JSON."""

from typing import Any

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model


class CallConfig(Model):
    """Most calls of an agent run on a handful of these."""

    __tablename__ = "call_configs"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
