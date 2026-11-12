"""What a host advises: an open model it serves, then what it lends, then the org's own key, else one to bring."""

from runtime.enums import Stage
from runtime.providers.catalog import Catalog
from runtime.providers.service.advice import Advised, Served, advise, list_served
from runtime.providers.service.keyring import Keyring
from tests.conftest import configured
from tests.fakes import acme

THE_30B = "nemotron-3.5-lightning:30b-a3b"


def served_row() -> Catalog:
    """Every stage on acme, its thinking at a server of this host's, the 30B the model it leads with."""
    row = configured().model_dump(mode="json")
    row["tuning"][f"llm/{acme.ACME}"] = {"options": {"base_url": "http://127.0.0.1:11434/v1"}}
    row["recommended"] = {f"llm/{acme.ACME}": [THE_30B, "gemma4:12b"]}
    return Catalog.model_validate(row)


def stage_of(advised: list[Advised], stage: Stage) -> Advised:
    return next(one for one in advised if one.stage == stage)


async def test_the_servers_of_the_row_are_asked_and_the_best_measured_model_they_hold_is_advised() -> None:
    """The thinking's server lists its models; the first the row leads with that it holds is the choice, on no key."""
    asked: list[str] = []

    async def listed(url: str) -> tuple[str, ...]:
        asked.append(url)
        return ("bge-m3", "gemma4:12b", THE_30B)

    served = await list_served(served_row(), listed)
    assert asked == ["http://127.0.0.1:11434/v1"] and served.on_this_host
    thinking = stage_of(advise(served_row(), Keyring(), served), Stage.llm)
    assert (thinking.choice, thinking.runs_on) == (f"{acme.ACME}/{THE_30B}", "served here")
    assert thinking.served == ("bge-m3", "gemma4:12b", THE_30B)


async def test_a_server_that_does_not_answer_serves_nothing() -> None:
    """A row whose server is down advises as if it served nothing: the next rule decides."""

    async def silent(_url: str) -> tuple[str, ...]:
        return ()

    served = await list_served(served_row(), silent)
    thinking = stage_of(advise(served_row(), Keyring(), served), Stage.llm)
    assert thinking.runs_on == "needs a key"


def test_what_the_host_lends_comes_before_the_orgs_own_key_and_a_key_to_bring_comes_last() -> None:
    """Lent by the host, the org runs it on nothing of its own; else on its own key; else it must bring one."""
    nothing_served = Served()
    lent = advise(configured(), Keyring(box={acme.ACME: "box-key"}, lends=None), nothing_served)
    assert {one.runs_on for one in lent} == {"lent by the runtime"}
    assert stage_of(lent, Stage.llm).choice == f"{acme.ACME}/{acme.MODEL}"
    not_lent = Keyring(box={acme.ACME: "box-key"}, own={acme.ACME: "own-key"}, lends=frozenset())
    assert {one.runs_on for one in advise(configured(), not_lent, nothing_served)} == {"your org's key"}
    bring = advise(configured(), Keyring(box={acme.ACME: "box-key"}, lends=frozenset()), nothing_served)
    assert {one.runs_on for one in bring} == {"needs a key"}
    assert stage_of(bring, Stage.tts).choice == f"{acme.ACME}/{acme.VOICE}"
