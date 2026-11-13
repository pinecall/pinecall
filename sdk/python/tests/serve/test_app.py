"""The project's voice app in its serve entry: loaded after the agents it imports, and told."""

import io
import json
from pathlib import Path

import pytest

from pinecall.serve._app import described, load_app, loaded
from pinecall.serve._loading import CannotServe, Flags, Served

AGENT = '''
from pinecall import Agent


class FrontDesk(Agent):
    """You answer the clinic's phone."""
'''

APP = """
from pinecall import voice_app
from pinecall_agents.front_desk.agent import FrontDesk

app = voice_app("brightside").line("+14155550134", FrontDesk).page("ui/dist")
"""


def project(root: Path, app: str = APP) -> Flags:
    folder = root / "agents" / "front-desk"
    folder.mkdir(parents=True)
    (folder / "agent.py").write_text(AGENT, encoding="utf-8")
    (root / "app.py").write_text(app, encoding="utf-8")
    return Flags((Served(folder / "agent.py", "front-desk"),), app=root / "app.py")


def test_the_app_imports_its_agents_as_they_were_loaded_and_is_told_with_its_page(
    tmp_path: Path,
) -> None:
    flags = project(tmp_path)
    out = io.StringIO()
    assert described(flags, out) == 0
    assert json.loads(out.getvalue()) == {
        "name": "brightside",
        "page": {"dir": "ui/dist", "agent": "front-desk"},
    }
    classes, app = loaded(flags)
    assert app is not None
    assert app.lines[0].answers is classes[0][1]


def test_a_file_with_no_voice_app_or_an_app_naming_a_class_not_served_is_refused(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(CannotServe, match="is read as the project's voice app, and holds none"):
        load_app(tmp_path / "empty.py")
    other = APP.replace(
        "from pinecall_agents.front_desk.agent import FrontDesk",
        "from pinecall import Agent\n\nclass FrontDesk(Agent):\n    'Another.'",
    )
    with pytest.raises(CannotServe, match="no agent served here is that class"):
        loaded(project(tmp_path / "other", other))
