"""A definition as an SDK would declare it: refused when no call could run it, its tools, its blocks."""

import pytest

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.studio.schemas import Definition
from pinecall_runtime.studio.service import definition as defined


def clinic(**changes: object) -> Definition:
    """The clinic's front desk: one lookup by phone, and the patient's name and reason collected."""
    raw: dict[str, object] = {
        "instructions": "You answer the phone for Clínica Norte. The caller dials from {{call.from}}.",
        "greeting": {"say": "Clínica Norte, buen día."},
        "tools": [
            {
                "name": "findPatient",
                "description": "Finds the patient by phone.",
                "url": "https://agenda.example.com/patients/{phone}",
                "headers": [{"name": "Authorization", "value": "Bearer {{secrets.AGENDA_KEY}}"}],
                "params": [{"name": "phone", "description": "the caller's number"}],
            }
        ],
        "collect": {
            "fields": [
                {"name": "name", "description": "the patient's full name"},
                {"name": "reason", "required": False},
            ],
            "send_to": "https://agenda.example.com/calls",
        },
    }
    raw.update(changes)
    return Definition.model_validate(raw)


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
    ],
)
def test_a_definition_no_call_could_run_is_refused_with_a_sentence(changes: dict[str, object], said: str) -> None:
    """A reserved name, a URL off TLS, a name twice, an undeclared path parameter, a secret in a URL."""
    with pytest.raises(ValidationError, match=said.replace("{", r"\{").replace("}", r"\}")):
        defined.check(clinic(**changes), {"AGENDA_KEY"}, Env.sandbox)


def a_tool(**changes: object) -> dict[str, object]:
    """A tool with a header's secret, the way a definition holds one, with these fields changed."""
    return {"name": "a", "description": "x", "url": "https://a.example.com", **changes}


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"instructions": "Log in with {{secrets.AGENDA_KEY}}."}, "`instructions`"),
        ({"greeting": {"say": "Key {{secrets.AGENDA_KEY}}"}}, "`greeting.say`"),
        ({"tools": [a_tool(description="Needs {{ secrets.AGENDA_KEY }}")]}, "`tools.a.description`"),
        ({"tools": [a_tool(announce="One moment, {{secrets.AGENDA_KEY}}")]}, "`tools.a.announce`"),
        ({"tools": [a_tool(url="https://a.example.com/?k={{secrets.AGENDA_KEY}}")]}, "`tools.a.url`"),
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


def test_the_declaration_carries_the_greeting_the_tools_the_fields_and_the_hang_up() -> None:
    """What agent.configure sends: the HTTP tool, collect with every field optional, the fields as state."""
    declared = defined.declaration(clinic())
    assert declared.greeting is not None and declared.greeting.say == "Clínica Norte, buen día."
    tools = {tool.name: tool for tool in declared.tools or []}
    assert sorted(tools) == ["collect", "findPatient"]
    assert tools["findPatient"].parameters["required"] == ["phone"]
    assert tools["collect"].parameters["required"] == []
    assert [field.name for field in declared.state_fields or []] == ["name", "reason"]
    assert declared.hangup is not None


def test_the_identity_fills_the_calls_values_and_leaves_an_unknown_one_empty() -> None:
    """`{{call.from}}` is the caller; `{{metadata.nothing}}` is nothing at all."""
    text = defined.identity(clinic(), {"call": {"from": "+59899123456", "channel": "phone", "medium": "voice"}})
    assert text.startswith("You answer the phone for Clínica Norte. The caller dials from +59899123456.\n\n<rules>")
    assert "<protocols>" in text and "You are on a phone call." in text
    assert defined.rendered("a{{metadata.nothing}}b", {"metadata": {}}) == "ab"


def test_the_view_says_what_is_in_what_is_missing_and_when_to_close() -> None:
    """Missing the name: asked for. With the name, the optional reason is still asked, and the call may close."""
    asking = defined.view(clinic(), {})
    assert "Still to collect" in asking and "name (string, required)" in asking
    assert "Every required field is in" not in asking
    closing = defined.view(clinic(), {"name": "Ana Ruiz"})
    assert '- name: "Ana Ruiz"' in closing
    assert "reason (string, optional)" in closing
    assert "Every required field is in" in closing
    assert defined.is_complete(clinic(), {"name": "Ana Ruiz"})


def test_a_written_chat_on_a_website_is_told_markdown_is_fine() -> None:
    """The channel's rules follow the call: a website's text chat is not a phone call."""
    text = defined.identity(clinic(), {"call": {"channel": "web", "medium": "text"}})
    assert "written chat on a website" in text and "phone call" not in text.split("<channel>")[1]


def test_the_declaration_sends_only_what_the_definition_sets() -> None:
    """No `record` or `uses_knowledge` by default: a default sent would fix a setting the console owns."""
    dumped = defined.declaration(clinic(collect=None, greeting=None)).model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    assert set(dumped) == {"tools", "state_fields"}


def test_an_agent_that_collects_nothing_has_an_empty_view_and_no_collect_tool() -> None:
    """Instructions and tools alone: the view is the instructions' job."""
    plain = clinic(collect=None)
    assert defined.view(plain, {}) == ""
    assert [spec.name for spec in defined.tool_specs(plain)] == ["findPatient"]


def test_a_release_round_trips_and_one_that_is_not_a_definition_is_refused() -> None:
    """What is kept is read back as it was; anything else is refused with what did not fit."""
    assert defined.parsed(defined.dumped(clinic())) == clinic()
    with pytest.raises(ValidationError, match="a Studio release is a definition"):
        defined.parsed(b'{"instructions": ""}')
