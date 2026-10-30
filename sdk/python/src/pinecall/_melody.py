"""The hold melody a class declares: the file beside it, named by hash, shipped once registered."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

from pinecall._harness import folder_of
from pinecall.client import Client
from pinecall.errors import DeclarationRefused
from pinecall.wire._names import JsonObject

NOT_A_HOLD = (
    'hold is the melody: {"file": "hold.mp3", "after_s": 1.5}, {"after_s": …}, '
    '{"off": True} or "off"'
)
NO_SUCH_FILE = "hold names {path}, and there is no such file beside the class"


def hold_config_of(cls: type) -> dict[str, object]:
    """What `hold` declares, as the wire carries it: the file by hash, the wait, or silence."""
    declared: object = getattr(cls, "hold", None)
    if declared is None:
        return {}
    if declared == "off":
        return {"hold": {"off": True}}
    if not isinstance(declared, dict):
        raise DeclarationRefused(NOT_A_HOLD)
    given = cast("dict[str, object]", declared)
    hold: dict[str, object] = {}
    if given.get("after_s") is not None:
        hold["after_s"] = given["after_s"]
    if given.get("off") is True:
        hold["off"] = True
    if given.get("file") is not None:
        path, data = melody_of(cls, given)
        hold["clip"] = hashlib.sha256(data).hexdigest()
        hold["name"] = path.name
    return {"hold": hold}


def melody_of(cls: type, declared: dict[str, object]) -> tuple[Path, bytes]:
    """The file the class ships as its melody, read beside the class's own file."""
    named = declared.get("file")
    if not isinstance(named, str) or not named:
        raise DeclarationRefused(NOT_A_HOLD)
    folder = folder_of(cls)
    path = (folder / named if folder is not None else Path(named)).resolve()
    if not path.is_file():
        raise DeclarationRefused(NO_SUCH_FILE.format(path=path))
    return path, path.read_bytes()


# The door keeps the hash of what was uploaded: a second start with the same file sends nothing.
async def upload_declared_hold(
    client: Client, cls: type, slug: str, report: Callable[[str], None]
) -> None:
    """Ship the class's melody once the agent registers, unless the gateway holds that file."""
    declared: object = getattr(cls, "hold", None)
    if not isinstance(declared, dict):
        return
    hold = cast("dict[str, object]", declared)
    if hold.get("file") is None:
        return
    path, data = melody_of(cls, hold)
    sha256 = hashlib.sha256(data).hexdigest()
    held: JsonObject = await client.hold_audio(slug)
    if held.get("source_sha256") == sha256:
        return
    landed = await client.upload_hold_audio(slug, data, path.name)
    report(f"{path.name} uploaded as the hold melody · {landed.get('seconds', '?')} s")
