"""A task: what a tool asks the caller for mid-tool, given back with a tool of its own."""

import pytest

from pinecall import DeclarationRefused, GetEmail, GetName, GetPhone, task
from pinecall.tasks import asking_for, given_with, giving_tool, tasks_of


def test_a_task_is_refused_without_a_name_a_question_fields_or_a_check() -> None:
    with pytest.raises(DeclarationRefused, match="lowercase"):
        task("Plate", asks="the plate", fields={"plate": "it"}, check=lambda given: given)
    with pytest.raises(DeclarationRefused, match="says what it asks for"):
        task("plate", asks=" ", fields={"plate": "it"}, check=lambda given: given)
    with pytest.raises(DeclarationRefused, match="names what the model gives"):
        task("plate", asks="the plate", fields={}, check=lambda given: given)


def test_a_task_is_given_with_a_tool_named_after_it_that_takes_its_fields_as_words() -> None:
    spec = giving_tool(GetName)
    assert (given_with(GetName), spec.name) == ("give_name", "give_name")
    assert spec.parameters["required"] == ["first", "last"]
    assert "Never guess it" in spec.description


def test_the_model_is_told_what_is_missing_how_to_ask_and_which_tool_gives_it() -> None:
    said = asking_for(GetEmail)
    assert "it needs the caller's email address" in said
    assert "letter by letter" in said
    assert said.endswith("Then call give_email.")


def test_the_built_in_tasks_hand_the_tool_a_clean_value_and_refuse_a_wrong_one() -> None:
    assert GetEmail.check({"email": " Ana@Example.COM "}) == "ana@example.com"
    assert GetPhone.check({"number": "+1 (415) 555-0142"}) == "+14155550142"
    assert GetName.check({"first": " Ana ", "last": "Ruiz"}) == {"first": "Ana", "last": "Ruiz"}
    with pytest.raises(ValueError, match="not an email address"):
        GetEmail.check({"email": "ana at example"})
    with pytest.raises(ValueError, match="not a phone number"):
        GetPhone.check({"number": "12"})


def test_a_class_declares_its_tasks_as_a_list_of_tasks() -> None:
    class Desk:
        tasks = (GetEmail,)

    class Wrong:
        tasks = ("email",)

    assert tasks_of(Desk) == [GetEmail]
    with pytest.raises(DeclarationRefused, match="a list of tasks"):
        tasks_of(Wrong)
