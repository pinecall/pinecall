"""Knowledge bases over HTTP: pushed, listed, read a file at a time, and dropped."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.handles import TheSessions
from runtime.knowledge import schemas
from runtime.knowledge.auth import KnowledgeKey, TheEmbedder
from runtime.knowledge.service import bases
from runtime.postgres import Session

router = APIRouter()


# By path: a file of the base the push does not name is kept, so a file the console put stays
# through `docs push`; `replace` is the folder as the one truth, as a repository's push is.
@router.put("/v1/knowledge/{base}")
async def push_base(
    base: str,
    body: schemas.KnowledgePush,
    actor: KnowledgeKey,
    embedder: TheEmbedder,
    sessions: TheSessions,
    replace: Annotated[bool, Query()] = False,
) -> schemas.KnowledgePushed:
    """Put the folder's files into the base, keeping the others; `?replace=true` makes the base the folder."""
    files = [(item.path, item.text) for item in body.files]
    pushed = await bases.push_folder(
        sessions, embedder, actor.scope, base, files, language=body.language, replace=replace
    )
    return schemas.KnowledgePushed.of(pushed)


@router.get("/v1/knowledge")
async def list_bases(actor: KnowledgeKey, session: Session) -> schemas.KnowledgeList:
    """Every base the key's scope reads, its size, its model and when it was pushed."""
    listed = await bases.list_bases(session, actor.scope)
    return schemas.KnowledgeList(bases=[schemas.KnowledgeBase.of(item) for item in listed])


# Before `/{base}`, so "attached" is never read as a base's name.
@router.get("/v1/knowledge/attached")
async def list_attached_bases(actor: KnowledgeKey, session: Session) -> schemas.KnowledgeUses:
    """Each base some agent attaches, and the agents whose settings in the scope attach it."""
    attached = await bases.list_attached(session, actor.scope)
    return schemas.KnowledgeUses(bases=[schemas.KnowledgeUse.of(item) for item in attached])


@router.get("/v1/knowledge/{base}")
async def list_files(base: str, actor: KnowledgeKey, session: Session) -> schemas.KnowledgeFiles:
    """The base's files, each with its size and chunks, never its text."""
    files = await bases.list_files(session, actor.scope, base)
    return schemas.KnowledgeFiles(
        base=base, kept=bool(files), files=[schemas.KnowledgeFileRow.of(item) for item in files]
    )


@router.get("/v1/knowledge/{base}/files/{path:path}")
async def get_file(base: str, path: str, actor: KnowledgeKey, session: Session) -> schemas.KnowledgeFileRead:
    """One file of the base, text and all."""
    return schemas.KnowledgeFileRead.of(await bases.get_file(session, actor.scope, base, path))


@router.put("/v1/knowledge/{base}/files/{path:path}")
async def put_file(
    base: str,
    path: str,
    body: schemas.KnowledgeFilePut,
    actor: KnowledgeKey,
    embedder: TheEmbedder,
    sessions: TheSessions,
) -> schemas.KnowledgeFilePushed:
    """Put one file into the base, beginning the base when there is none; only it is cut."""
    put = await bases.put_file(sessions, embedder, actor.scope, base, path, body.text)
    return schemas.KnowledgeFilePushed.of(put)


@router.delete("/v1/knowledge/{base}/files/{path:path}", status_code=204)
async def delete_file(base: str, path: str, actor: KnowledgeKey, session: Session) -> None:
    """Take one file and its chunks out of the base, and the base with its last file."""
    await bases.delete_file(session, actor.scope, base, path)


@router.delete("/v1/knowledge/{base}", status_code=204)
async def delete_base(base: str, actor: KnowledgeKey, session: Session) -> None:
    """Drop the holder's own copy of the base and its chunks."""
    await bases.delete_base(session, actor.scope, base)
