"""A definition checked before it is kept: refused when no call could run it, and read back as it was written."""

import pytest

from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.studio.service import definition as defined
from tests.studio.factories import a_tool, clinic


def test_a_definition_whose_secrets_the_env_holds_is_accepted() -> None:
    """Every name once, https throughout, the secret set: nothing to say."""
    defined.check(clinic(), {"AGENDA_KEY"}, Env.sandbox)


@pytest.mark.parametrize(
    ("changes", "said"),
    [
        ({"tools": [{"name": "collect", "description": "x", "url": "https://a.example.com"}]}, "platform's own"),
        ({"tools": [{"name": "a", "description": "x", "url": "http://a.example.com"}] * 1}, "https"),
        (
            {"tools": [{"name": "a", "description": "x", "url": "https://a.example.com"}] * 2},
            "two tools are called a",
        ),
        ({"tools": [{"name": "a", "description": "x", "url": "https://a.example.com/{id}"}]}, "{id}"),
        (
            {"tools": [{"name": "a", "description": "x", "url": "https://a.example.com/?k={{secrets.AGENDA_KEY}}"}]},
            "outside a header",
        ),
        (
            {"tools": [a_tool(params=[{"name": "n", "type": "integer", "enum": ["1", "2"]}])]},
            "a closed list is a string's",
        ),
        ({"tools": [a_tool(fixed=[{"name": "k", "value": 1}, {"name": "k", "value": 2}])]}, "two fixed fields"),
        (
            {"tools": [a_tool(params=[{"name": "k"}], fixed=[{"name": "k", "value": "x"}])]},
            "a parameter the model fills and a field fixed here",
        ),
        ({"collect": {"fields": [{"name": "n", "type": "boolean", "enum": ["yes"]}]}}, "data collection: n lists"),
    ],
)
def test_a_definition_no_call_could_run_is_refused_with_a_sentence(changes: dict[str, object], said: str) -> None:
    """A reserved name, a URL off TLS, a name twice, a path param undeclared, a secret in a URL, a list on a number."""
    with pytest.raises(ValidationError, match=said.replace("{", r"\{").replace("}", r"\}")):
        defined.check(clinic(**changes), {"AGENDA_KEY"}, Env.sandbox)


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"instructions": "Log in with {{secrets.AGENDA_KEY}}."}, "`instructions`"),
        ({"greeting": {"say": "Key {{secrets.AGENDA_KEY}}"}}, "`greeting.say`"),
        ({"tools": [a_tool(description="Needs {{ secrets.AGENDA_KEY }}")]}, "`tools.a.description`"),
        ({"tools": [a_tool(announce="One moment, {{secrets.AGENDA_KEY}}")]}, "`tools.a.announce`"),
        ({"tools": [a_tool(url="https://a.example.com/?k={{secrets.AGENDA_KEY}}")]}, "`tools.a.url`"),
        ({"tools": [a_tool(fixed=[{"name": "k", "value": "{{secrets.AGENDA_KEY}}"}])]}, "`tools.a.fixed.k.value`"),
        ({"tools": [a_tool(failed="Sorry, {{secrets.AGENDA_KEY}}")]}, "`tools.a.failed`"),
        (
            {"tools": [a_tool(params=[{"name": "p", "description": "the {{secrets.AGENDA_KEY}}"}])]},
            "`tools.a.params.p.description`",
        ),
        (
            {"collect": {"fields": [{"name": "n", "description": "{{secrets.AGENDA_KEY}}"}]}},
            "`collect.fields.n.description`",
        ),
        ({"collect": {"fields": [{"name": "n"}], "closing": "Say {{secrets.AGENDA_KEY}}."}}, "`collect.closing`"),
        (
            {"collect": {"fields": [{"name": "n"}], "send_to": "https://a.example.com/{{secrets.AGENDA_KEY}}"}},
            "`collect.send_to`",
        ),
    ],
)
def test_a_secret_named_anywhere_but_a_headers_value_is_refused_with_one_sentence_saying_where(
    changes: dict[str, object], where: str
) -> None:
    """The instructions, a description, a greeting, a URL: every string of the definition, one sentence."""
    with pytest.raises(ValidationError) as refused:
        defined.check(clinic(**changes), {"AGENDA_KEY"}, Env.sandbox)
    assert str(refused.value) == (
        f"{where} names {{{{secrets.AGENDA_KEY}}}} outside a header: a secret travels in a header alone"
    )


def test_a_secret_in_a_headers_value_stays_where_it_belongs() -> None:
    """The one place a secret may be named, on a tool and on data collection."""
    headed = {"collect": {"fields": [{"name": "n"}], "headers": [{"name": "X-Key", "value": "{{secrets.AGENDA_KEY}}"}]}}
    defined.check(clinic(**headed), {"AGENDA_KEY"}, Env.sandbox)


def test_a_secret_the_env_lacks_is_refused_naming_where_it_is_set() -> None:
    """A deploy to production checks production's secrets: a missing one is said before a call."""
    with pytest.raises(ValidationError, match=r"AGENDA_KEY, which production has none of: set it there.*Secrets"):
        defined.check(clinic(), set(), Env.production)


def test_a_release_round_trips_and_one_that_is_not_a_definition_is_refused() -> None:
    """What is kept is read back as it was; anything else is refused with what did not fit."""
    assert defined.parse(defined.dump(clinic())) == clinic()
    with pytest.raises(ValidationError, match="a Studio release is a definition"):
        defined.parse(b'{"instructions": ""}')
