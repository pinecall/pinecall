"""A class that declares `docs` pushes the folder beside it once registered, file by file."""

from pathlib import Path

import pytest

from pinecall import Agent
from pinecall._docs import markdown_under, push_declared_docs
from pinecall.client import Client
from pinecall.wire._names import JsonObject


def folder(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_every_markdown_file_under_the_folder_is_read_by_its_path_and_nothing_for_no_folder(
    tmp_path: Path,
) -> None:
    where = folder(
        tmp_path,
        {
            "docs/hours.md": "# Hours",
            "docs/policies/insurance.md": "# Insurance",
            "docs/notes.txt": "no",
        },
    )
    assert markdown_under(where / "docs") == [
        {"path": "hours.md", "text": "# Hours"},
        {"path": "policies/insurance.md", "text": "# Insurance"},
    ]
    assert markdown_under(where / "nowhere") == []


async def test_the_folder_beside_a_class_that_declares_docs_is_pushed_and_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed: list[tuple[str, list[JsonObject]]] = []

    async def push_knowledge(self: Client, base: str, files: list[JsonObject]) -> JsonObject:
        pushed.append((base, files))
        return {"base": base, "chunks": 7, "kept": 2, "language": "es", "took_ms": 1.0}

    monkeypatch.setattr(Client, "push_knowledge", push_knowledge)
    where = folder(tmp_path, {"docs/hours.md": "# Hours", "agent.py": "x"})
    reads = type("Reads", (Agent,), {"docs": {"base": "front-desk", "k": 4}, "__doc__": "Reads."})

    def beside(_cls: type) -> Path:
        return where

    monkeypatch.setattr("pinecall._docs.folder_of", beside)
    said: list[str] = []
    await push_declared_docs(Client("https://gw", "pk_test", None), reads, said.append)
    assert pushed == [("front-desk", [{"path": "hours.md", "text": "# Hours"}])]
    assert said == ["front-desk  1 file(s) pushed · 7 chunk(s) · 2 kept"]


async def test_nothing_is_pushed_for_a_class_with_no_base_or_a_folder_that_is_not_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def push_knowledge(self: Client, base: str, files: list[JsonObject]) -> JsonObject:
        raise AssertionError("nothing should be pushed")

    monkeypatch.setattr(Client, "push_knowledge", push_knowledge)

    def beside(_cls: type) -> Path:
        return tmp_path

    monkeypatch.setattr("pinecall._docs.folder_of", beside)
    silent = type("Silent", (Agent,), {"__doc__": "Declares no base."})
    reads = type("Reads", (Agent,), {"docs": {"base": "front-desk"}, "__doc__": "Reads."})
    said: list[str] = []
    await push_declared_docs(Client("https://gw", "pk_test", None), silent, said.append)
    await push_declared_docs(Client("https://gw", "pk_test", None), reads, said.append)
    assert said == []
