"""The folder beside a class: its file's, and none for a class with no file."""

from pathlib import Path

from pinecall import Agent
from pinecall._beside import folder_of


def test_the_folder_beside_a_class_is_its_files() -> None:
    assert folder_of(Agent) == Path(__file__).resolve().parents[1] / "src" / "pinecall"


def test_a_class_with_no_file_has_no_folder() -> None:
    made = type("Made", (Agent,), {"__doc__": "Made in memory.", "__module__": "builtins"})

    assert folder_of(made) is None
