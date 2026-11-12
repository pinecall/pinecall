"""The JSON documents an agent's app publishes under a name, for any page to read with no key."""

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.repository import AgentDocumentRepository
from runtime.enums import Env
from runtime.exceptions import NotFound, ValidationError
from runtime.kit.text import a_mapping

# A name is a path segment a page asks for: short, lower case, nothing a URL would escape.
A_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
# Read by every visitor of a page, so small: a short list, not a database.
LARGEST = 64 * 1024


def check_name(name: str) -> str:
    """The name, when it is one a document may have."""
    if not A_NAME.match(name):
        raise ValidationError(
            f"a document's name is lower case letters, digits and dashes, 40 at most, from a letter: not {name!r}"
        )
    return name


async def publish_document(session: AsyncSession, scope: Scope, agent: str, name: str, raw: bytes) -> dict[str, Any]:
    """Publish a JSON object under its name, over the one before it; the document as it is kept."""
    try:
        body: object = json.loads(raw)
    except ValueError as bad:
        raise ValidationError("a document is one JSON object") from bad
    if not a_mapping(body):
        raise ValidationError("a document is one JSON object")
    row = await AgentDocumentRepository(session).put(scope.org, scope.env, agent, check_name(name), dict(body))
    return row.body


async def get_document(session: AsyncSession, *, org: str, env: Env, agent: str, name: str) -> dict[str, Any]:
    """The document the app published; NotFound while there is none."""
    row = await AgentDocumentRepository(session).find(org, env, agent, check_name(name))
    if row is None:
        raise NotFound(f"agent {agent} published no document {name} in {env}")
    return row.body
