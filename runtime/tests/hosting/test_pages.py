"""An app's page: the name it is served by, read back to its app, and the folder a release is checked for."""

import io
import tarfile

import pytest

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.hosting.service.apps import App, checked_source
from pinecall_runtime.hosting.service.pages import Page, checked_page, label_of, named_by

DOMAIN = "app.example.com"


def _sources(files: dict[str, bytes]) -> bytes:
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        for path, content in files.items():
            member = tarfile.TarInfo(path)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    return packed.getvalue()


def test_a_page_is_named_by_its_app_its_org_and_its_env_and_the_name_reads_back() -> None:
    live = App(org="org_1", env=Env.production, name="front-desk")
    tried = App(org="org_1", env=Env.sandbox, name="front-desk")
    assert label_of("brightside-dental", live) == "front-desk--brightside-dental"
    assert label_of("brightside-dental", tried) == "front-desk--brightside-dental--sandbox"
    assert named_by(f"front-desk--brightside-dental.{DOMAIN}", DOMAIN) == (
        "brightside-dental",
        "front-desk",
        Env.production,
    )
    assert named_by(f"Front-Desk--brightside-dental--sandbox.{DOMAIN}", DOMAIN) == (
        "brightside-dental",
        "front-desk",
        Env.sandbox,
    )


@pytest.mark.parametrize(
    "host",
    [
        "cloud.example.com",
        f"front-desk.{DOMAIN}",
        f"front-desk--org--staging.{DOMAIN}",
        f"a--b--sandbox--more.{DOMAIN}",
        f"--org.{DOMAIN}",
        f"deeper.front-desk--org.{DOMAIN}",
        DOMAIN,
    ],
)
def test_any_other_host_names_no_page(host: str) -> None:
    assert named_by(host, DOMAIN) is None


def test_a_release_sent_with_no_page_has_none() -> None:
    source = checked_source(_sources({"package.json": b"{}"}))
    assert checked_page(source, None, None, "front-desk--org") is None


def test_a_page_is_its_folder_inside_the_sources_and_its_agent() -> None:
    source = checked_source(_sources({"package.json": b"{}", "ui/dist/index.html": b"<!doctype html>"}))
    assert checked_page(source, "ui/dist/", "front-desk", "front-desk--org") == Page(dir="ui/dist", agent="front-desk")


def test_a_page_is_refused_with_no_index_outside_the_project_half_said_or_too_long_a_name() -> None:
    source = checked_source(_sources({"package.json": b"{}", "ui/dist/app.js": b"1"}))
    with pytest.raises(ValidationError, match=r"has no index\.html"):
        checked_page(source, "ui/dist", "front-desk", "front-desk--org")
    with pytest.raises(ValidationError, match="inside the project"):
        checked_page(source, "../site", "front-desk", "front-desk--org")
    with pytest.raises(ValidationError, match="both its folder and its agent"):
        checked_page(source, "ui/dist", None, "front-desk--org")
    with pytest.raises(ValidationError, match="too long a name"):
        checked_page(source, "ui/dist", "front-desk", "a" * 64)
