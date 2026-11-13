"""A voice app: its lines, its rules, what its agents share, the page, and what it hears."""

from typing import cast

import pytest

from pinecall import Agent, CallLine, DeclarationRefused, Heard, _config, flow, voice_app
from pinecall.flows import Step
from pinecall.wire._names import JsonObject


class FrontDesk(Agent):
    """You answer the clinic's phone."""


class Billing(Agent):
    """You answer questions about bills."""

    takes = "questions about a bill"


class Greets(Agent):
    """It greets on its own."""

    greeting = "Hola."


def billing(_: CallLine) -> type:
    return Billing


@flow("remind-visit")
async def remind(visit: JsonObject, step: Step) -> None:
    await step.sleep("1h")


def test_an_app_is_named_like_its_folder_and_keeps_its_clock_in_a_real_zone() -> None:
    assert voice_app("brightside", timezone="America/Los_Angeles").timezone == "America/Los_Angeles"
    with pytest.raises(DeclarationRefused, match="lowercase"):
        voice_app("Brightside")
    with pytest.raises(DeclarationRefused, match="IANA zone"):
        voice_app("brightside", timezone="Mars/Olympus")


def test_a_line_is_a_number_with_its_country_code_answered_once_by_an_agent() -> None:
    app = voice_app("brightside").line("+1 (415) 555-0134", FrontDesk, greeting="Brightside.")
    assert [(line.number, line.answers, line.greeting) for line in app.lines] == [
        ("+14155550134", FrontDesk, "Brightside.")
    ]
    with pytest.raises(DeclarationRefused, match="country code"):
        app.line("555 0134", FrontDesk)
    with pytest.raises(DeclarationRefused, match="a line of brightside already"):
        app.line("+14155550134", Billing)
    with pytest.raises(DeclarationRefused, match="same greeting"):
        app.line("+14155550135", FrontDesk)


def test_a_teammate_says_what_it_takes_and_a_line_that_chooses_names_its_fallback() -> None:
    app = voice_app("brightside")
    with pytest.raises(DeclarationRefused, match="says nothing of what it takes"):
        app.line("+14155550134", FrontDesk, team=[Greets])
    with pytest.raises(DeclarationRefused, match="names its fallback"):
        app.line("+14155550134", billing, team=[Billing])
    app.line("+14155550134", billing, team=[Billing], fallback=FrontDesk)
    assert app.team_of(Billing) == [FrontDesk, Billing]
    assert app.choosing(FrontDesk) is not None
    assert app.numbers_of(FrontDesk) == ["+14155550134"]


def test_an_agent_is_named_by_the_slug_it_is_served_as_wherever_a_class_is() -> None:
    _config.keep_served("front-desk", FrontDesk)
    _config.keep_served("billing", Billing)
    app = voice_app("brightside").line("+14155550134", "front-desk", team=["billing"])
    assert (app.lines[0].answers, app.lines[0].team) == (FrontDesk, (Billing,))
    app.line("+14155550135", billing, team=["billing"], fallback="front-desk").page(
        "ui/dist", answers="billing"
    )
    assert app.choosing(FrontDesk) is not None
    assert app.paged is not None
    assert app.paged.answers is Billing
    with pytest.raises(DeclarationRefused, match="no agent here is served as front-desc"):
        voice_app("other").line("+14155550134", "front-desc")
    with pytest.raises(DeclarationRefused, match="no agent here is served as billin"):
        voice_app("other").line("+14155550134", FrontDesk, team=["billin"])


def test_what_the_app_declares_for_its_agents_and_a_setting_both_declare_is_refused() -> None:
    app = (
        voice_app("brightside", timezone="America/Los_Angeles")
        .line("+14155550134", FrontDesk, greeting="Brightside.")
        .rule("Never quote a price.")
        .silence(after="8s", say="¿Sigues ahí?", times=2)
    )
    declared = app.declares(FrontDesk)
    assert declared["greeting"] == {"say": "Brightside."}
    assert declared["timezone"] == "America/Los_Angeles"
    assert declared["idle"] == {"says": ["¿Sigues ahí?"], "after_s": 8.0, "times": 2}
    asked = cast("dict[str, list[dict[str, object]]]", declared["judges"])
    assert [one["name"] for one in asked["own"]] == ["app-rule-1"]
    with pytest.raises(DeclarationRefused, match="keep one of the two"):
        voice_app("other").line("+14155550199", Greets, greeting="Otra.").declares(Greets)


def test_a_page_is_a_folder_inside_the_project_reaching_the_first_lines_agent() -> None:
    app = voice_app("brightside").line("+14155550134", FrontDesk).page("./ui/dist/")
    assert app.paged is not None
    assert (app.paged.dir, app.paged.answers) == ("ui/dist", FrontDesk)
    with pytest.raises(DeclarationRefused, match="inside the project"):
        voice_app("other").line("+14155550134", FrontDesk).page("../elsewhere")
    with pytest.raises(DeclarationRefused, match="write a line before the page"):
        voice_app("other").page("ui/dist")


def test_a_page_may_be_kept_to_one_environment_and_no_other_word_names_one() -> None:
    app = voice_app("brightside").line("+14155550134", FrontDesk).page("site", only="sandbox")
    assert app.paged is not None
    assert app.paged.only == "sandbox"
    everywhere = voice_app("both").line("+14155550134", FrontDesk).page("site").paged
    assert everywhere is not None
    assert everywhere.only is None
    with pytest.raises(DeclarationRefused, match="in one"):
        voice_app("other").line("+14155550134", FrontDesk).page("site", only="staging")


async def test_an_entry_reaches_its_handlers_by_name_a_logged_line_by_its_own() -> None:
    heard: list[tuple[str | None, JsonObject]] = []

    async def booked(call: Heard, data: JsonObject) -> None:
        heard.append((call.id, data))

    def fails(_: Heard, __: JsonObject) -> None:
        raise RuntimeError("down")

    failed: list[str] = []
    app = voice_app("brightside").on("visit.booked", fails).on("visit.booked", booked)
    custom: JsonObject = {"name": "visit.booked", "data": {"id": 7}}
    await app.heard("custom", "CA_1", "front-desk", custom, lambda name, _: failed.append(name))
    assert (heard, failed) == ([("CA_1", {"id": 7})], ["visit.booked"])


def test_a_flow_handed_to_on_is_started_by_the_entry_and_two_of_one_name_are_refused() -> None:
    app = voice_app("brightside").on("visit.booked", remind)
    assert (app.started_by("visit.booked"), app.flows()) == ([remind], [remind])

    @flow("remind-visit")
    async def again(visit: JsonObject, step: Step) -> None:
        await step.sleep("1h")

    with pytest.raises(DeclarationRefused, match="two flows of brightside"):
        app.on("visit.moved", again)


def test_a_silence_is_seconds_and_words() -> None:
    with pytest.raises(DeclarationRefused, match="silence is"):
        voice_app("brightside").silence(after="soon", say="¿Hola?")
