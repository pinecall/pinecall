"""An app's page: the name it is served by, read back to its app, and the folder a release is checked for."""

import pytest

from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.hosting.service.apps import App
from runtime.hosting.service.pages import Page, check_page, label_page, read_page_name
from runtime.hosting.service.releases import check_source
from tests.hosting.factories import tarball

DOMAIN = "app.example.com"


def test_a_page_is_named_by_its_app_its_org_and_its_env_and_the_name_reads_back() -> None:
    live = App(org="org_1", env=Env.production, name="front-desk")
    tried = App(org="org_1", env=Env.sandbox, name="front-desk")
    assert label_page("brightside-dental", live) == "front-desk--brightside-dental"
    assert label_page("brightside-dental", tried) == "front-desk--brightside-dental--sandbox"
    assert read_page_name(f"front-desk--brightside-dental.{DOMAIN}", DOMAIN) == (
        "brightside-dental",
        "front-desk",
        Env.production,
    )
    assert read_page_name(f"Front-Desk--brightside-dental--sandbox.{DOMAIN}", DOMAIN) == (
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
    assert read_page_name(host, DOMAIN) is None


def test_a_release_sent_with_no_page_has_none() -> None:
    source = check_source(tarball({"package.json": b"{}"})).data
    assert check_page(source, None, None, "front-desk--org") is None


def test_a_page_is_its_folder_inside_the_sources_and_its_agent() -> None:
    source = check_source(tarball({"package.json": b"{}", "ui/dist/index.html": b"<!doctype html>"})).data
    assert check_page(source, "ui/dist/", "front-desk", "front-desk--org") == Page(dir="ui/dist", agent="front-desk")


def test_a_page_is_refused_with_no_index_outside_the_project_half_said_or_too_long_a_name() -> None:
    source = check_source(tarball({"package.json": b"{}", "ui/dist/app.js": b"1"})).data
    with pytest.raises(ValidationError, match=r"has no index\.html"):
        check_page(source, "ui/dist", "front-desk", "front-desk--org")
    with pytest.raises(ValidationError, match="inside the project"):
        check_page(source, "../site", "front-desk", "front-desk--org")
    with pytest.raises(ValidationError, match="both its folder and its agent"):
        check_page(source, "ui/dist", None, "front-desk--org")
    with pytest.raises(ValidationError, match="too long a name"):
        check_page(source, "ui/dist", "front-desk", "a" * 64)
