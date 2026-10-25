"""The JSON documents an agent's app publishes under a name, for any page to read with no key."""

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.models import AgentDocument
from pinecall_runtime.agents.repository import AgentDocumentRepository
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError

# A name is a path segment a page asks for: short, lower case, nothing a URL would escape.
A_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
# Read by every visitor of a page, so small: a short list, not a database.
LARGEST = 64 * 1024

BAD_NAME = "a document's name is lower case letters, digits and dashes, 40 at most, from a letter: not {name!r}"
NONE_PUBLISHED = "agent {agent} published no document {name} in {env}"


def check_name(name: str) -> str:
    """The name, when it is one a document may have."""
    if not A_NAME.match(name):
        raise ValidationError(BAD_NAME.format(name=name))
    return name


async def publish_document(
    session: AsyncSession, *, org: str, env: Env, agent: str, name: str, body: dict[str, Any]
) -> AgentDocument:
    """Publish the document under its name, over the one before it."""
    return await AgentDocumentRepository(session).put(org, env, agent, check_name(name), body)


async def get_document(session: AsyncSession, *, org: str, env: Env, agent: str, name: str) -> AgentDocument:
    """The document the app published; NotFound while there is none."""
    row = await AgentDocumentRepository(session).get(org, env, agent, check_name(name))
    if row is None:
        raise NotFound(NONE_PUBLISHED.format(agent=agent, name=name, env=env))
    return row
