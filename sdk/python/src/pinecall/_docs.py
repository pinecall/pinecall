"""The `docs/` folder a class declares as its base, pushed when the agent registers."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

from pinecall._harness import folder_of
from pinecall.client import Client
from pinecall.wire._names import JsonObject

# Where an agent's documents are, beside its class.
DOCS_FOLDER = "docs"


def markdown_under(folder: Path) -> list[JsonObject]:
    """Every Markdown file under the folder, its path as the base keeps it; none for no folder."""
    if not folder.is_dir():
        return []
    return [
        {"path": path.relative_to(folder).as_posix(), "text": path.read_text(encoding="utf-8")}
        for path in sorted(folder.rglob("*.md"))
        if path.is_file()
    ]


# A class that declares `docs` owns its base: the folder beside it is pushed once the agent
# registers, the base's other files kept, so a start or a deploy needs no `pinecall docs push`.
async def push_declared_docs(client: Client, cls: type, report: Callable[[str], None]) -> None:
    """Push the class's `docs/` folder into the base it declares; nothing without either."""
    declared: object = getattr(cls, "docs", None)
    base = cast("dict[str, object]", declared).get("base") if isinstance(declared, dict) else None
    folder = folder_of(cls)
    if not isinstance(base, str) or folder is None:
        return
    files = markdown_under(folder / DOCS_FOLDER)
    if not files:
        return
    pushed = await client.push_knowledge(base, files)
    kept = pushed.get("kept", 0)
    said = f"{base}  {len(files)} file(s) pushed · {pushed.get('chunks', 0)} chunk(s)"
    report(f"{said} · {kept} kept" if kept else said)
